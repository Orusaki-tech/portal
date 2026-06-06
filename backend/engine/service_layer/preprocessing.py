"""
Satellite imagery preprocessing pipeline.

Provides a modular chain of preprocessing steps that run after scene
download and before VRT mosaic / clipping in the COG pipeline.

Available steps (registered in STEP_REGISTRY):
  - cloud_mask               : Per-pixel cloud/shadow masking (SCL band, QA_PIXEL, s2cloudless)
  - speckle_filter           : SAR speckle reduction (Lee filter)
  - pansharpen               : Pan-sharpening (Brovey, PCA, IHS)
  - resample                 : Resolution harmonisation for auxiliary bands
  - atmospheric_correction   : Dark Object Subtraction (DOS) for L1 sources
  - radiometric_normalization: Histogram matching across overlapping scenes (batch)
  - topographic_correction   : C-correction using DEM + sun angles (per-scene)
"""

from __future__ import annotations

import json
import logging
import os
from abc import ABC, abstractmethod
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Base classes
# ---------------------------------------------------------------------------


class PreprocessingStep(ABC):
    """A single preprocessing operation applied to a downloaded scene raster."""

    name: str
    is_batch_step: bool = False

    def __init__(self, **options: Any) -> None:
        self.options = options

    @abstractmethod
    def process(
        self,
        input_path: str,
        aux_paths: dict[str, str],
        tmpdir: str,
    ) -> str:
        """Return path to the processed raster."""

    def process_batch(
        self,
        input_paths: list[str],
        scenes: list,
        all_aux_paths: list[dict[str, str]],
        tmpdir: str,
    ) -> list[str]:
        """Override for batch steps that need all scenes simultaneously."""
        return input_paths


class Pipeline:
    """Ordered chain of preprocessing steps."""

    def __init__(self, steps: list[PreprocessingStep]) -> None:
        self.steps = steps

    def run(self, input_path: str, aux_paths: dict[str, str], tmpdir: str) -> str:
        current = input_path
        for step in self.steps:
            if getattr(step, 'is_batch_step', False):
                continue
            try:
                current = step.process(current, aux_paths, tmpdir)
            except StepNotAvailableError:
                logger.warning("Step %s not available — skipping", step.name)
                continue
            except Exception:
                logger.exception("Step %s failed — skipping", step.name)
                continue
        return current

    def batch_process(
        self,
        input_paths: list[str],
        scenes: list,
        all_aux_paths: list[dict[str, str]],
        tmpdir: str,
    ) -> list[str]:
        """Run batch steps (those needing all scenes simultaneously) across all inputs.

        Only steps with ``is_batch_step = True`` are executed.
        """
        current = list(input_paths)
        for step in self.steps:
            if not getattr(step, 'is_batch_step', False):
                continue
            try:
                current = step.process_batch(current, scenes, all_aux_paths, tmpdir)
            except Exception:
                logger.exception("Batch step %s failed — skipping", step.name)
                continue
        return current


class StepNotAvailableError(RuntimeError):
    """Raised when a step's dependencies are not met (e.g. missing Python package)."""


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

STEP_REGISTRY: dict[str, type[PreprocessingStep]] = {}


def register_step(name: str) -> Any:
    def decorator(cls: type[PreprocessingStep]) -> type[PreprocessingStep]:
        STEP_REGISTRY[name] = cls
        cls.name = name
        return cls
    return decorator


# ---------------------------------------------------------------------------
# ResampleStep — align auxiliary bands to primary raster resolution
# ---------------------------------------------------------------------------


@register_step("resample")
class ResampleStep(PreprocessingStep):
    """Resample auxiliary bands to match the primary raster's resolution."""

    def process(self, input_path: str, aux_paths: dict[str, str], tmpdir: str) -> str:
        import rasterio
        from rasterio.enums import Resampling

        with rasterio.open(input_path) as src:
            target_h, target_w = src.height, src.width
            target_crs = src.crs
            target_transform = src.transform

        for name, path in list(aux_paths.items()):
            with rasterio.open(path) as aux:
                if aux.res[0] == src.res[0] and aux.res[1] == src.res[1]:
                    continue
                is_scl = "scl" in name.lower()
                out = os.path.join(tmpdir, f"{name}_resampled.tif")
                resampled = aux.read(
                    1,
                    out_shape=(target_h, target_w),
                    resampling=Resampling.nearest if is_scl else Resampling.bilinear,
                )
                with rasterio.open(
                    out, "w",
                    driver="GTiff",
                    height=target_h,
                    width=target_w,
                    count=1,
                    dtype=resampled.dtype,
                    crs=target_crs,
                    transform=target_transform,
                ) as dst:
                    dst.write(resampled, 1)
                aux_paths[name] = out

        return input_path


# ---------------------------------------------------------------------------
# CloudMaskStep — per-pixel cloud and cloud-shadow masking
# ---------------------------------------------------------------------------

SCL_MASK_VALUES = [3, 7, 8, 9, 10]   # shadow, unclassified, medium/high cloud, cirrus


def _mask_via_scl(input_path: str, scl_path: str, mask_values: list[int], tmpdir: str) -> str:
    import rasterio
    from rasterio.enums import Resampling

    with rasterio.open(input_path) as vis:
        with rasterio.open(scl_path) as scl:
            scl_data = scl.read(1)
            if scl.res[0] != vis.res[0]:
                scl_data = scl.read(
                    1, out_shape=(vis.height, vis.width),
                    resampling=Resampling.nearest,
                )
            mask = np.isin(scl_data, mask_values)
            data = vis.read()
            for band in data:
                band[mask] = 0
            out = os.path.join(tmpdir, "masked_visual.tif")
            with rasterio.open(out, "w", **vis.profile) as dst:
                dst.write(data)
    return out


def _mask_via_qa_pixel(input_path: str, qa_path: str, cloud_bits: list[int], tmpdir: str) -> str:
    import rasterio
    from rasterio.enums import Resampling

    with rasterio.open(input_path) as src:
        with rasterio.open(qa_path) as qa_src:
            qa = qa_src.read(1)
            if qa_src.res[0] != src.res[0]:
                qa = qa_src.read(1, out_shape=(src.height, src.width), resampling=Resampling.nearest)
            mask = np.zeros_like(qa, dtype=bool)
            for bit in cloud_bits:
                mask |= (qa & (1 << bit)) != 0
            cloud_conf = (qa >> 8) & 0x3
            mask |= cloud_conf >= 1
            data = src.read()
            for band in data:
                band[mask] = 0
            out = os.path.join(tmpdir, "masked.tif")
            with rasterio.open(out, "w", **src.profile) as dst:
                dst.write(data)
    return out


def _mask_via_s2cloudless(input_path: str, band_paths: dict[str, str], tmpdir: str) -> str:
    try:
        from sentinelhub import CloudDetector
    except ImportError:
        raise StepNotAvailableError("s2cloudless requires the 'sentinelhub' package")

    import rasterio
    from rasterio.enums import Resampling

    detector = CloudDetector()
    band_names = ["B01", "B02", "B03", "B04", "B05", "B06", "B07", "B08", "B8A", "B09", "B11", "B12"]
    bands = {}
    ref_shape = None
    for name in band_names:
        path = band_paths.get(name)
        if not path or not os.path.exists(path):
            continue
        with rasterio.open(path) as src:
            if ref_shape is None:
                ref_shape = (src.height, src.width)
            if (src.height, src.width) != ref_shape:
                data = src.read(1, out_shape=ref_shape, resampling=Resampling.bilinear)
            else:
                data = src.read(1)
            bands[name] = data

    if len(bands) < 4:
        raise StepNotAvailableError("Not enough spectral bands for s2cloudless")

    proba = detector.get_cloud_probabilities(bands)
    mask = proba > 0.4

    with rasterio.open(input_path) as vis:
        data = vis.read()
        for band in data:
            band[mask] = 0
        out = os.path.join(tmpdir, "masked_s2cloudless.tif")
        with rasterio.open(out, "w", **vis.profile) as dst:
            dst.write(data)
    return out


@register_step("cloud_mask")
class CloudMaskStep(PreprocessingStep):
    """Per-pixel cloud and cloud-shadow masking.

    Methods (auto-detected):
      scl         — Sentinel-2 Scene Classification Layer (default, no deps)
      qa_pixel    — Landsat QA_PIXEL bitmask
      s2cloudless — ML-based (requires sentinelhub package, opt-in)
    """

    def process(self, input_path: str, aux_paths: dict[str, str], tmpdir: str) -> str:
        method = self.options.get("method", "scl")
        aux_key = self.options.get("aux_key", "scl")

        if method == "scl":
            scl_path = aux_paths.get(aux_key)
            if not scl_path:
                raise StepNotAvailableError(f"SCL auxiliary band '{aux_key}' not available")
            mask_values = self.options.get("mask_values", SCL_MASK_VALUES)
            return _mask_via_scl(input_path, scl_path, mask_values, tmpdir)

        if method == "qa_pixel":
            qa_path = aux_paths.get(aux_key)
            if not qa_path:
                raise StepNotAvailableError(f"QA band '{aux_key}' not available")
            cloud_bits = self.options.get("cloud_bits", [3, 4])
            return _mask_via_qa_pixel(input_path, qa_path, cloud_bits, tmpdir)

        if method == "s2cloudless":
            return _mask_via_s2cloudless(input_path, aux_paths, tmpdir)

        raise ValueError(f"Unknown cloud_mask method '{method}'")


# ---------------------------------------------------------------------------
# SpeckleFilterStep — SAR speckle reduction (Lee filter)
# ---------------------------------------------------------------------------


def _lee_filter(
    array: np.ndarray,
    window_size: int = 7,
    noise_variance: float | None = None,
) -> np.ndarray:
    from scipy.ndimage import uniform_filter

    local_mean = uniform_filter(array, size=window_size)
    local_sq_mean = uniform_filter(array ** 2, size=window_size)
    local_var = np.maximum(local_sq_mean - local_mean ** 2, 0)

    if noise_variance is None:
        noise_variance = np.mean(local_var)

    weight = np.where(local_var > noise_variance,
                      (local_var - noise_variance) / local_var, 0.0)

    return local_mean + weight * (array - local_mean)


@register_step("speckle_filter")
class SpeckleFilterStep(PreprocessingStep):
    """SAR speckle reduction using the Lee adaptive filter.

    Applies independently to each band (VV, VH, VV/VH ratio).
    """

    def process(self, input_path: str, aux_paths: dict[str, str], tmpdir: str) -> str:
        import rasterio

        with rasterio.open(input_path) as src:
            profile = src.profile.copy()
            data = src.read().astype(np.float32)
            window = self.options.get("window_size", 7)
            for b in range(data.shape[0]):
                data[b] = _lee_filter(data[b], window_size=window)
            profile.update(dtype=rasterio.float32)
            out = os.path.join(tmpdir, "despeckled.tif")
            with rasterio.open(out, "w", **profile) as dst:
                dst.write(data)
        return out


# ---------------------------------------------------------------------------
# PanSharpenStep — three algorithms
# ---------------------------------------------------------------------------


def _brovey(ms_path: str, pan_path: str, tmpdir: str) -> str:
    import rasterio
    from rasterio.enums import Resampling

    with rasterio.open(ms_path) as ms:
        with rasterio.open(pan_path) as pan:
            pan_resampled = pan.read(
                1, out_shape=(ms.height, ms.width),
                resampling=Resampling.bilinear,
            ).astype(np.float32)
            data = ms.read().astype(np.float32)
            rgb_sum = np.sum(data[:3], axis=0) + 1e-10
            for b in range(min(3, data.shape[0])):
                data[b] = data[b] * pan_resampled / (rgb_sum / 3)
            profile = ms.profile.copy()
            profile.update(dtype=rasterio.float32)
            out = os.path.join(tmpdir, "pansharpened_brovey.tif")
            with rasterio.open(out, "w", **profile) as dst:
                dst.write(data)
    return out


def _pca_pansharpen(ms_path: str, pan_path: str, tmpdir: str) -> str:
    import rasterio
    from rasterio.enums import Resampling
    from sklearn.decomposition import PCA

    with rasterio.open(ms_path) as ms:
        with rasterio.open(pan_path) as pan:
            pan_resampled = pan.read(
                1, out_shape=(ms.height, ms.width),
                resampling=Resampling.bilinear,
            ).astype(np.float32)
            data = ms.read().astype(np.float32)
            n_bands, h, w = data.shape
            pixels = data.reshape(n_bands, -1).T
            pca = PCA(n_components=n_bands)
            transformed = pca.fit_transform(pixels)
            pc1 = transformed[:, 0].reshape(h, w)
            pan_flat = pan_resampled.reshape(-1)
            from scipy.stats import linregress
            slope, intercept, *_ = linregress(pc1.reshape(-1), pan_flat)
            pan_matched = (pan_flat - intercept) / slope
            transformed[:, 0] = pan_matched
            inverse = pca.inverse_transform(transformed).T.reshape(n_bands, h, w)
            profile = ms.profile.copy()
            profile.update(dtype=rasterio.float32)
            out = os.path.join(tmpdir, "pansharpened_pca.tif")
            with rasterio.open(out, "w", **profile) as dst:
                dst.write(inverse.astype(np.float32))
    return out


def _ihs_pansharpen(ms_path: str, pan_path: str, tmpdir: str) -> str:
    import rasterio
    from rasterio.enums import Resampling

    with rasterio.open(ms_path) as ms:
        with rasterio.open(pan_path) as pan:
            pan_resampled = pan.read(
                1, out_shape=(ms.height, ms.width),
                resampling=Resampling.bilinear,
            ).astype(np.float32)
            data = ms.read([1, 2, 3]).astype(np.float32)
            r, g, b = data[0], data[1], data[2]

            # IHS spherical transform
            i = (r + g + b) / 3.0 + 1e-10
            h = np.arctan2(b - g, 2 * r - g - b)
            s = np.sqrt(2) / 3.0 * np.sqrt((r - g) ** 2 + (g - b) ** 2 + (b - r) ** 2) / i

            # Histogram match pan to intensity
            pan_mean, pan_std = pan_resampled.mean(), pan_resampled.std()
            i_mean, i_std = i.mean(), i.std()
            pan_matched = i_mean + (pan_resampled - pan_mean) * (i_std / pan_std)

            # Replace I with matched pan
            i_new = pan_matched

            # Inverse IHS
            r_new = i_new + (2.0 / 3.0) * (s * np.cos(h) * i_new / (i + 1e-10) * i)
            g_new = i_new - (1.0 / 3.0) * (s * np.cos(h) * i_new / (i + 1e-10) * i) \
                    + (1.0 / np.sqrt(3)) * (s * np.sin(h) * i_new / (i + 1e-10) * i)
            b_new = i_new - (1.0 / 3.0) * (s * np.cos(h) * i_new / (i + 1e-10) * i) \
                    - (1.0 / np.sqrt(3)) * (s * np.sin(h) * i_new / (i + 1e-10) * i)

            stacked = np.stack([r_new, g_new, b_new]).astype(np.float32)
            profile = ms.profile.copy()
            profile.update(count=3, dtype=rasterio.float32)
            out = os.path.join(tmpdir, "pansharpened_ihs.tif")
            with rasterio.open(out, "w", **profile) as dst:
                dst.write(stacked)
    return out


@register_step("pansharpen")
class PanSharpenStep(PreprocessingStep):
    """Pan-sharpening: merge high-res panchromatic with multi-spectral bands.

    Algorithms:
      brovey — fast, colour-preserving (default)
      pca    — PCA-based, most accurate
      ihs    — IHS transform, RGB only
    """

    def process(self, input_path: str, aux_paths: dict[str, str], tmpdir: str) -> str:
        pan_path = aux_paths.get("pan")
        if not pan_path:
            raise StepNotAvailableError("Panchromatic band not available")
        algorithm = self.options.get("algorithm", "brovey")
        if algorithm == "brovey":
            return _brovey(input_path, pan_path, tmpdir)
        elif algorithm == "pca":
            return _pca_pansharpen(input_path, pan_path, tmpdir)
        elif algorithm == "ihs":
            return _ihs_pansharpen(input_path, pan_path, tmpdir)
        raise ValueError(f"Unknown pansharpen algorithm '{algorithm}'")


# ---------------------------------------------------------------------------
# AtmosphericCorrectionStep — Dark Object Subtraction (DOS)
# ---------------------------------------------------------------------------


@register_step("atmospheric_correction")
class AtmosphericCorrectionStep(PreprocessingStep):
    """Dark Object Subtraction (DOS) atmospheric correction for L1 sources.

    Finds the dark object (1st percentile) in each band and subtracts it
    to remove additive atmospheric path radiance.
    """

    def process(self, input_path: str, aux_paths: dict[str, str], tmpdir: str) -> str:
        import rasterio

        with rasterio.open(input_path) as src:
            profile = src.profile.copy()
            data = src.read().astype(np.float32)
            for b in range(data.shape[0]):
                band = data[b]
                dark_val = np.percentile(band[band > 0], 1) if (band > 0).any() else 0
                data[b] = np.maximum(band - dark_val, 0)
            profile.update(dtype=rasterio.float32)
            out = os.path.join(tmpdir, "atm_corrected.tif")
            with rasterio.open(out, "w", **profile) as dst:
                dst.write(data)
        return out


# ---------------------------------------------------------------------------
# RadiometricNormalizationStep — histogram matching across overlapping scenes
# ---------------------------------------------------------------------------


@register_step("radiometric_normalization")
class RadiometricNormalizationStep(PreprocessingStep):
    """Histogram matching across overlapping scenes for radiometric consistency.

    Uses the lowest-cloud-cover scene as the reference and matches all other
    scenes via cumulative distribution function (CDF) interpolation per band.
    """

    is_batch_step = True

    def process(self, input_path: str, aux_paths: dict[str, str], tmpdir: str) -> str:
        return input_path

    def process_batch(
        self,
        input_paths: list[str],
        scenes: list,
        all_aux_paths: list[dict[str, str]],
        tmpdir: str,
    ) -> list[str]:
        import rasterio

        if len(input_paths) < 2:
            return input_paths

        ref_idx = self._select_reference(scenes)

        with rasterio.open(input_paths[ref_idx]) as ref_src:
            ref_data = ref_src.read()

        results = list(input_paths)
        for i in range(len(input_paths)):
            if i == ref_idx:
                continue
            with rasterio.open(input_paths[i]) as src:
                data = src.read().astype(np.float32)
                profile = src.profile.copy()
                for b in range(data.shape[0]):
                    data[b] = self._match_band(data[b], ref_data[b])
                out = os.path.join(tmpdir, f"normalized_{i}.tif")
                with rasterio.open(out, "w", **profile) as dst:
                    dst.write(data)
                results[i] = out
        return results

    @staticmethod
    def _select_reference(scenes: list) -> int:
        best_idx = 0
        best_cc = float("inf")
        for i, s in enumerate(scenes):
            cc = getattr(s, "cloud_cover", None)
            if cc is not None and cc < best_cc:
                best_cc = cc
                best_idx = i
        return best_idx

    @staticmethod
    def _compute_cdf(data: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Compute CDF of non-zero pixels for a single band."""
        valid = data[data > 0]
        if len(valid) == 0:
            return np.array([0.0]), np.array([0.0])
        bins = np.linspace(float(data.min()), float(data.max()), 1024)
        hist, _ = np.histogram(valid, bins=bins)
        cdf = hist.cumsum(dtype=np.float64)
        cdf = cdf / cdf[-1]
        return bins[:-1], cdf

    @staticmethod
    def _match_band(target: np.ndarray, reference: np.ndarray) -> np.ndarray:
        src_bins, src_cdf = RadiometricNormalizationStep._compute_cdf(target)
        ref_bins, ref_cdf = RadiometricNormalizationStep._compute_cdf(reference)
        mapping = np.interp(src_cdf, ref_cdf, ref_bins)
        flat = target.ravel().copy()
        valid_mask = flat > 0
        if valid_mask.any():
            flat[valid_mask] = np.interp(flat[valid_mask], src_bins, mapping)
        return flat.reshape(target.shape).astype(np.float32)


# ---------------------------------------------------------------------------
# TopographicCorrectionStep — C-correction using DEM + sun angles
# ---------------------------------------------------------------------------


def _compute_illumination(
    slope: np.ndarray,
    aspect: np.ndarray,
    sun_azimuth_rad: float,
    sun_elevation_rad: float,
) -> np.ndarray:
    """Cosine of solar incidence angle (local illumination)."""
    return (
        np.sin(sun_elevation_rad) * np.cos(slope)
        + np.cos(sun_elevation_rad) * np.sin(slope)
        * np.cos(sun_azimuth_rad - aspect)
    )


@register_step("topographic_correction")
class TopographicCorrectionStep(PreprocessingStep):
    """Topographic correction (C-correction) using a DEM and sun angle metadata.

    Requires aux_paths:
      - dem: path to DEM GeoTIFF (e.g. Copernicus GLO-30)
      - scene_props: path to JSON file with ``sun_azimuth`` and ``sun_elevation``
    """

    def process(self, input_path: str, aux_paths: dict[str, str], tmpdir: str) -> str:
        import rasterio
        from rasterio.enums import Resampling
        from scipy.ndimage import sobel

        dem_path = aux_paths.get("dem")
        if not dem_path:
            raise StepNotAvailableError("DEM not available for topographic correction")

        props_path = aux_paths.get("scene_props")
        if not props_path:
            raise StepNotAvailableError("Scene properties not available")
        with open(props_path) as f:
            props = json.load(f)

        sun_azimuth = props.get("sun_azimuth")
        sun_elevation = props.get("sun_elevation")
        if sun_azimuth is None or sun_elevation is None:
            raise StepNotAvailableError("Sun azimuth/elevation not available")

        az_rad = np.radians(sun_azimuth)
        el_rad = np.radians(sun_elevation)
        solar_zenith_rad = np.radians(90.0 - sun_elevation)
        cos_sz = np.cos(solar_zenith_rad)

        with rasterio.open(input_path) as src:
            data = src.read().astype(np.float32)
            profile = src.profile.copy()
            height, width = src.height, src.width
            transform = src.transform
            crs = src.crs

        with rasterio.open(dem_path) as dem_src:
            dem = dem_src.read(
                1,
                out_shape=(height, width),
                resampling=Resampling.bilinear,
            ).astype(np.float32)

        dem = np.nan_to_num(dem, nan=0.0)

        res_x = abs(transform[0])
        res_y = abs(transform[4])

        if crs and crs.is_geographic:
            cy = transform[5] + height * transform[4] / 2
            cos_lat = abs(np.cos(np.radians(cy)))
            res_x_m = res_x * 111320.0 * cos_lat
            res_y_m = res_y * 111320.0
        else:
            res_x_m = res_x
            res_y_m = res_y

        dz_dx = sobel(dem, axis=1) / (2.0 * res_x_m + 1e-10)
        dz_dy = sobel(dem, axis=0) / (2.0 * res_y_m + 1e-10)

        slope = np.arctan(np.sqrt(dz_dx**2 + dz_dy**2))
        aspect = np.arctan2(dz_dy, -dz_dx)
        aspect[aspect < 0] += 2.0 * np.pi

        cos_i = _compute_illumination(slope, aspect, az_rad, el_rad)
        cos_i = np.maximum(cos_i, 0.01)

        cos_i_flat = cos_i.ravel()
        for b in range(data.shape[0]):
            band = data[b].ravel()
            valid = (band > 0) & (cos_i_flat > 0.01)
            if valid.sum() < 100:
                continue
            A = np.vstack([cos_i_flat[valid], np.ones_like(cos_i_flat[valid])]).T
            a_b, b_b = np.linalg.lstsq(A, band[valid], rcond=None)[0]
            C = b_b / (abs(a_b) + 1e-10)
            corrected = band * (C + cos_sz) / (C + cos_i_flat)
            data[b] = np.maximum(corrected.reshape(height, width), 0)

        profile.update(dtype=rasterio.float32)
        out = os.path.join(tmpdir, "topo_corrected.tif")
        with rasterio.open(out, "w", **profile) as dst:
            dst.write(data)
        return out


# ---------------------------------------------------------------------------
# Pipeline builder
# ---------------------------------------------------------------------------


def build_pipeline(
    source_id: str,
    source_config: dict[str, Any],
    user_opts: dict[str, Any] | None = None,
) -> Pipeline | None:
    """Construct a preprocessing Pipeline from source config + user overrides.

    Parameters
    ----------
    source_id : str
        Identifier of the imagery source (e.g. "sentinel-2-l2a").
    source_config : dict
        The source configuration dict from SOURCE_CONFIG.
    user_opts : dict or None
        Optional user-specified overrides from the API request.
        Structure: {step_name: {option: value}}.

    Returns
    -------
    Pipeline or None if the source has no pipeline defined.
    """
    pipeline_cfg = source_config.get("pipeline")
    if not pipeline_cfg:
        return None

    user_opts = user_opts or {}
    steps = []

    for step_cfg in pipeline_cfg:
        step_name = step_cfg["step"]
        step_cls = STEP_REGISTRY.get(step_name)
        if not step_cls:
            logger.warning("Unknown preprocessing step '%s' — skipping", step_name)
            continue

        # Merge user overrides into step defaults
        defaults = dict(step_cfg.get("defaults", {}))
        overrides = dict(user_opts.get(step_name, {}))
        options = {**defaults, **overrides}
        steps.append(step_cls(**options))

    return Pipeline(steps) if steps else None
