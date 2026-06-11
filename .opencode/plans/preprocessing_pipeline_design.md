# Satellite Preprocessing Pipeline — Design

## 1. Architecture

New module: `backend/engine/service_layer/preprocessing.py`

### 1.1 Core Interfaces

```python
class PreprocessingStep(ABC):
    name: str
    @abstractmethod
    def process(self, input_path: str, aux_paths: dict[str, str],
                tmpdir: str, options: dict) -> str: ...

class Pipeline:
    steps: list[PreprocessingStep]
    def run(self, input_path: str, aux_paths: dict[str, str], tmpdir: str) -> str:
        current = input_path
        for step in self.steps:
            current = step.process(current, aux_paths, tmpdir, step.options)
        return current

def build_pipeline(source_id: str, user_opts: dict | None = None) -> Pipeline | None:
    cfg = SOURCE_CONFIG.get(source_id)
    if not cfg or "pipeline" not in cfg:
        return None
    steps = []
    for step_cfg in cfg["pipeline"]:
        step_cls = STEP_REGISTRY[step_cfg["step"]]
        options = {**step_cfg.get("defaults", {}), **(user_opts or {}).get(step_cfg["step"], {})}
        steps.append(step_cls(**options))
    return Pipeline(steps)
```

### 1.2 Integration into `_generate_clipped_cog_sync` (Point A: after download, before VRT)

```python
inputs = [acquire_local_path(s, tmpdir) for s in scenes]

# === NEW: Preprocessing ===
pipeline = build_pipeline(source_id, user_preprocessing_opts)
if pipeline:
    for i, (scene, input_path) in enumerate(zip(scenes, inputs)):
        aux_paths = {}
        if hasattr(scene, 'aux_urls'):
            for aux_name, aux_url in scene.aux_urls.items():
                aux_item = Scene(id=aux_name, url=aux_url, ...)
                aux_paths[aux_name] = acquire_local_path(aux_item, tmpdir)
        inputs[i] = pipeline.run(input_path, aux_paths, tmpdir)

# === Current: VRT + clip ===
if len(inputs) == 1:
    input_path = inputs[0]
else:
    input_path = _build_vrt_mosaic(inputs, tmpdir)
cog_path, size_bytes = _generate_clipped_cog(input_path, geojson, buffer_meters, tmpdir)
```

## 2. Per-Source Pipeline Config

Extend `SOURCE_CONFIG` in `cog_service.py`:

| Source | Steps | Auxiliary assets |
|--------|-------|-----------------|
| **naip** | *(none)* | — |
| **sentinel-2-l2a** | `cloud_mask` (method=scl) | `scl` ← `SCL` asset |
| **landsat-c2-l2** | `cloud_mask` (method=qa_pixel) | `qa_pixel` ← `qa_pixel` asset |
| **sentinel-1-rtc** | `speckle_filter` (method=lee) | — |
| **cbers-4-mux** | `cloud_mask` (method=scl, if available) | `scl` ← `SCL` |
| **amazonia-1-wfi** | *(none)* | — |
| **cop-dem-glo-30** | *(none)* | — |
| **commercial (varies)** | Pipeline from auto-detected processing level | — |

## 3. Step Implementations

### 3.1 CloudMaskStep — Three Methods

#### A. `scl` — Sentinel-2 Scene Classification Layer

SCL pixel values to mask:
- 3 = Cloud Shadows
- 7 = Clouds Low Probability / Unclassified (conservative)
- 8 = Clouds Medium Probability
- 9 = Clouds High Probability
- 10 = Thin Cirrus

```python
def _mask_via_scl(visual_path, scl_path, mask_values, tmpdir) -> str:
    with rasterio.open(visual_path) as vis:
        with rasterio.open(scl_path) as scl:
            scl_data = scl.read(1)
            if scl.res[0] != vis.res[0]:  # SCL is 20m, visual is 10m
                scl_data = scl.read(1, out_shape=(vis.height, vis.width),
                                     resampling=Resampling.nearest)
            mask = np.isin(scl_data, mask_values)
            vis_data = vis.read()
            for band in vis_data:
                band[mask] = 0
            out = os.path.join(tmpdir, "masked_visual.tif")
            with rasterio.open(out, "w", **vis.profile) as dst:
                dst.write(vis_data)
    return out
```

#### B. `qa_pixel` — Landsat QA bitmask

QA_PIXEL bits:
- Bit 3: Cloud
- Bit 4: Cloud Shadow
- Bits 8-9: Cloud Confidence (1=medium, 2=high)

```python
def _mask_via_qa_pixel(input_path, qa_path, cloud_bits, tmpdir) -> str:
    with rasterio.open(input_path) as src:
        with rasterio.open(qa_path) as qa_src:
            qa = qa_src.read(1)
            mask = np.zeros_like(qa, dtype=bool)
            for bit in cloud_bits:
                mask |= (qa & (1 << bit)) != 0
            cloud_conf = (qa >> 8) & 0x3   # medium+ confidence
            mask |= cloud_conf >= 1
            data = src.read()
            for band in data:
                band[mask] = 0
            out = os.path.join(tmpdir, "masked.tif")
            with rasterio.open(out, "w", **src.profile) as dst:
                dst.write(data)
    return out
```

#### C. `s2cloudless` — ML-based (opt-in, needs `sentinelhub`)

```python
def _mask_via_s2cloudless(band_paths, tmpdir) -> str:
    try:
        from sentinelhub import CloudDetector
    except ImportError:
        raise StepNotAvailableError("s2cloudless not installed, fall back to SCL")
    detector = CloudDetector()
    # Read bands B01-B12, stack, run inference → probability map
    # Threshold at 0.4 → binary mask
    # Apply mask to visual
```

**Decision**: SCL = default (zero deps, authoritative, always available). s2cloudless = opt-in only when `sentinelhub` package is present and user selects it. The step auto-detects which method is possible.

### 3.2 SpeckleFilterStep — Lee Filter (SAR)

For Sentinel-1 RTC (VV + VH bands). Each band filtered independently.

```python
def lee_filter(array: np.ndarray, window_size: int = 7, noise_variance: float | None = None) -> np.ndarray:
    from scipy.ndimage import uniform_filter
    local_mean = uniform_filter(array, size=window_size)
    local_sq_mean = uniform_filter(array ** 2, size=window_size)
    local_var = np.maximum(local_sq_mean - local_mean ** 2, 0)
    if noise_variance is None:
        noise_variance = np.mean(local_var)
    weight = np.where(local_var > noise_variance,
                      (local_var - noise_variance) / local_var, 0.0)
    return local_mean + weight * (array - local_mean)

class SpeckleFilterStep(PreprocessingStep):
    def process(self, input_path, aux_paths, tmpdir, options):
        with rasterio.open(input_path) as src:
            profile = src.profile.copy()
            data = src.read().astype(np.float32)
            for b in range(data.shape[0]):
                data[b] = lee_filter(data[b], window_size=options.get("window_size", 7))
            profile.update(dtype=rasterio.float32)
            out = os.path.join(tmpdir, "despeckled.tif")
            with rasterio.open(out, "w", **profile) as dst:
                dst.write(data)
        return out
```

### 3.3 PanSharpenStep — Three Algorithms

**Note**: Landsat C2 L2 on Planetary Computer doesn't have the 15m pan band. The pan band is in the L1 collection (`landsat-c2-l1` asset `pan` or `B8`). Pan-sharpening needs either:
a. Cross-collection query (L2 for SR bands + L1 for pan band)
b. Only available when user uploads their own data with pan band

| Algorithm | Quality | Speed | Band requirement |
|-----------|---------|-------|-----------------|
| Brovey | Good | Fast | 3+ multispectral + pan |
| PCA | Best | Moderate | 3+ multispectral + pan |
| IHS | Good | Fast | RGB only + pan |

```python
class PanSharpenStep(PreprocessingStep):
    def process(self, input_path, aux_paths, tmpdir, options):
        alg = options.get("algorithm", "brovey")
        if alg == "brovey":
            return _brovey(input_path, aux_paths["pan"], tmpdir)
        elif alg == "pca":
            return _pca(input_path, aux_paths["pan"], tmpdir)
        elif alg == "ihs":
            return _ihs(input_path, aux_paths["pan"], tmpdir)
```

**Brovey**: `ms_band * pan / mean(sum_of_rgb_ms)`
**PCA**: Replace PC1 with histogram-matched pan, inverse transform
**IHS**: Replace Intensity with histogram-matched pan, inverse transform

### 3.4 ResampleStep — Auxiliary band alignment

Always run before per-pixel processing to ensure matching resolution:

```python
class ResampleStep(PreprocessingStep):
    def process(self, input_path, aux_paths, tmpdir, options) -> tuple[str, dict]:
        with rasterio.open(input_path) as src:
            for name, path in aux_paths.items():
                with rasterio.open(path) as aux:
                    if aux.res[0] != src.res[0]:
                        resampled = aux.read(1, out_shape=(src.height, src.width),
                                             resampling=Resampling.nearest if "scl" in name else Resampling.bilinear)
                        out = os.path.join(tmpdir, f"{name}_resampled.tif")
                        with rasterio.open(out, "w", driver="GTiff", height=src.height,
                                           width=src.width, count=1, dtype=resampled.dtype,
                                           crs=src.crs, transform=src.transform) as dst:
                            dst.write(resampled, 1)
                        aux_paths[name] = out
        return input_path, aux_paths
```

## 4. User Options (Frontend)

New section in `ImageryModal.tsx`:

```typescript
interface PreprocessingOptions {
  cloud_mask: boolean             // default: true
  cloud_mask_method: "auto" | "scl" | "qa_pixel" | "s2cloudless"
  speckle_filter: boolean        // default: true (for SAR)
  pansharpen: false | "brovey" | "pca" | "ihs"
}
```

Sent in fetch request:

```typescript
const res = await fetchApi("/api/imagery/fetch", {
  source_id: activeSourceId,
  geojson: feature.geometry,
  buffer_meters: buffer,
  date_from: dateFrom,
  date_to: dateTo,
  max_cloud_cover: maxCloudCover,
  preprocessing: {
    cloud_mask: true,
    cloud_mask_method: "auto",
    speckle_filter: true,
    pansharpen: false,
  },
})
```

Backend merges user options with step defaults:

```python
user_pp = body.preprocessing or {}
pipeline = build_pipeline(source_id, user_pp)
```

## 5. Commercial Providers — Processing Level

| Level | Description | Pipeline |
|-------|-------------|----------|
| L1/L1B | Radiometrically + geometrically corrected | AtmCorrection + CloudMask |
| L2 | Surface reflectance | CloudMask only |
| L3 | Orthorectified, mosaiced | CloudMask only |
| L4 | Thematic product | None |

Auto-detected from provider API metadata response. If level unknown, use conservative default (L2 = CloudMask only).

```python
LEVEL_PIPELINES = {
    "L1": Pipeline(steps=[ACStep(), CloudMaskStep(method="threshold")]),
    "L1B": Pipeline(steps=[ACStep(), CloudMaskStep(method="threshold")]),
    "L2": Pipeline(steps=[CloudMaskStep(method="qa_pixel")]),
}
```

## 6. Implementation Order

| # | What | Files |
|---|------|-------|
| 1 | `preprocessing.py` — base classes + Pipeline + registry | New file |
| 2 | `ResampleStep` | Same |
| 3 | `CloudMaskStep` (SCL + QA_PIXEL) | Same |
| 4 | `SpeckleFilterStep` (Lee) | Same |
| 5 | `PanSharpenStep` (Brovey + PCA + IHS) | Same |
| 6 | Extend `SOURCE_CONFIG` with pipeline + auxiliary_assets | `cog_service.py` |
| 7 | Extend `Scene` dataclass with `aux_urls` | `cog_service.py` |
| 8 | Modify `_query_stac_scenes` to fetch auxiliary URLs | `cog_service.py` |
| 9 | Hook preprocessing into `_generate_clipped_cog_sync` | `cog_service.py` |
| 10 | Add `preprocessing` param to `POST /api/imagery/fetch` | `api.py` |
| 11 | Add `preprocessing` field to `ImageryFetchRequest` model | `api.py` (models) |
| 12 | UI controls in `ImageryModal.tsx` | Frontend |
| 13 | Commercial provider level detection | `commercial_providers.py` |

## 7. Key Decisions

| Decision | Choice | Why |
|----------|--------|-----|
| Cloud mask default | SCL band | Zero computation, authoritative ESA product, always available |
| Cloud mask fallback | s2cloudless | ML-based, needs `sentinelhub`, opt-in only |
| SAR speckle filter | Lee (7×7) | Adaptive, edge-preserving, simple implementation via `scipy.ndimage` |
| Pan-sharpening | Brovey / PCA / IHS | User-selectable; Brovey for speed, PCA for accuracy, IHS for RGB |
| Landsat pan band | Cross-collection query | L1 collection has 15m pan; fetch alongside L2 SR bands |
| User controls | Pass `preprocessing` object in fetch | Merged with defaults per source |
| Commercial level | Auto-detect from provider metadata | Conservative fallback = L2 pipeline |

## 8. Error Handling

| Scenario | Behavior |
|----------|----------|
| SCL/QA_PIXEL band missing | Skip CloudMaskStep, log warning, proceed with original |
| sentinelhub not installed | Fall back to SCL method, log info |
| Pan band unavailable | Skip PanSharpenStep, log in response metadata |
| User opts out (e.g. `cloud_mask: false`) | Skip that step entirely |
| Resolution mismatch | ResampleStep runs first to align all bands |
| Processing fails unexpectly | Catch exception, fall back to raw download, log error, proceed |
