#!/usr/bin/env python3
"""Build the complete semantic similarity notebook for Kenya crisis detection."""
import json, os

def _lines(src):
    parts = src.split("\n")
    return [p + "\n" for p in parts]

def md(src):
    return {"cell_type": "markdown",
            "metadata": {},
            "source": _lines(src)}

def code(src):
    return {"cell_type": "code",
            "metadata": {},
            "execution_count": None,
            "outputs": [],
            "source": _lines(src)}

cells = []

# =========================================================================
# CELL 0: TITLE
# =========================================================================
cells.append(md("""# 5. Semantic Similarity — Kenya Crisis Detection

**Goal:** Identify admin2 regions in Kenya that semantically resemble known drought crisis zones, using fused spectral (Sentinel-2) and vector (conflict events, population density) features attached to connected components.

**Pipeline:**
1. Load Kenya admin2 boundaries + FEWS NET crisis labels (2016–2017)
2. Download UCDP conflict events + WorldPop population density for Kenya
3. For each known crisis admin2 region: clip Sentinel-2 Q2 2016 → compute NDVI/NDWI/NDBI → SLIC segmentation → extract per-component features
4. Spatial join: attach conflict event counts + population density onto each component
5. Build a **crisis centroid** in fused feature space from crisis-zone components
6. Repeat for test admin2 regions → compute cosine similarity to crisis centroid
7. Aggregate scores per admin2 region → rank by crisis resemblance
8. Validate against FEWS NET 2017 labels → ROC AUC

**Data sources (all open / free / programmatically accessible):**

| Data | Source | How |
|------|--------|-----|
| Kenya admin2 boundaries | `../ken_admin2.geojson` | in repo |
| Sentinel-2 L2A (10m) | Microsoft Planetary Computer STAC | `pystac-client` |
| FEWS NET IPC phases | fdw.fews.net API | `gpd.read_file(url)` |
| UCDP conflict events | HDX CSV | `httpx` download |
| WorldPop population | data.worldpop.org | `httpx` download |
"""))

# =========================================================================
# CELL 1: INSTALL
# =========================================================================
cells.append(md("""## 0. Install dependencies

Run the cell below if any packages are missing. You may need to **restart the kernel** after installation.
"""))

cells.append(code("""import subprocess, sys, os

req = ["geopandas", "pandas", "rio-tiler", "scikit-image", "scikit-learn",
       "matplotlib", "pystac-client", "planetary-computer", "httpx", "rasterio"]

missing = []
for pkg in req:
    name = pkg.replace("-", "_")
    r = subprocess.run([sys.executable, "-c", f"import {name}"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        missing.append(pkg)

if missing:
    print(f"Installing missing packages: {missing}")
    pip = subprocess.run([sys.executable, "-m", "pip", "install"] + missing,
                         capture_output=True, text=True)
    if pip.returncode == 0:
        print("Done. Restart kernel (Kernel → Restart) before proceeding.")
    else:
        print(f"Error:\\n{pip.stderr}")
else:
    print("All packages already installed.")
"""))

# =========================================================================
# CELL 2: IMPORTS
# =========================================================================
cells.append(md("## 1. Setup & imports"))

cells.append(code("""import json, os, sys, warnings, math
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from shapely.geometry import shape, box, Point
from shapely.ops import unary_union

from pystac_client import Client as StacClient
from planetary_computer import sign as pc_sign
import httpx

from rio_tiler.io import COGReader as Reader
from rio_tiler.errors import TileOutsideBounds

from skimage.segmentation import slic
from skimage.measure import regionprops_table
from skimage.transform import resize
from skimage.io import imsave

from sklearn.preprocessing import StandardScaler
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.metrics import roc_auc_score, roc_curve

import rasterio
import geopandas as gpd

warnings.filterwarnings("ignore")
PROJECT_ROOT = os.path.join(os.getcwd(), "..")
sys.path.insert(0, PROJECT_ROOT)

print("All imports OK")
"""))

# =========================================================================
# CELL 3: LOAD ADMIN2
# =========================================================================
cells.append(md("## 2. Load Kenya admin2 boundaries"))

cells.append(code("""admin2_path = os.path.join(PROJECT_ROOT, "ken_admin2.geojson")
if not os.path.exists(admin2_path):
    admin2_path = "../ken_admin2.geojson"
admin2 = gpd.read_file(admin2_path)
print(f"Admin2 regions: {len(admin2)}")
print(f"Columns: {list(admin2.columns)}")
admin2.head(3)
"""))

# =========================================================================
# CELL 4: FEWS NET
# =========================================================================
cells.append(md("## 3. Download FEWS NET crisis data (2016–2017)"))

cells.append(code("""# FEWS NET IPC phases: 1=Minimal, 2=Stressed, 3=Crisis, 4=Emergency, 5=Famine
dates_2016 = [f"2016-{m:02d}" for m in range(1, 13)]
dates_2017 = [f"2017-{m:02d}" for m in range(1, 13)]

fews_records = []
for d in dates_2016 + dates_2017:
    url = (f"https://fdw.fews.net/api/ipcphasemap/"
           f"?country=KE&scenario=CS&collection_date={d}-01&format=geojson")
    try:
        df = gpd.read_file(url)
        df["period"] = d
        fews_records.append(df)
        print(f"  {d}: {len(df)} polygons")
    except Exception as e:
        print(f"  {d}: no data ({e})")

fews = pd.concat(fews_records, ignore_index=True)
phase_col = [c for c in fews.columns if "phase" in c.lower() or "ipc" in c.lower()]
print(f"\\nPhase column: {phase_col}")
if phase_col:
    print(fews[phase_col[0]].value_counts().sort_index())
print(f"Total records: {len(fews)}")
"""))

# =========================================================================
# CELL 5: CONFLICT DATA
# =========================================================================
cells.append(md("## 4. Download UCDP conflict events (Kenya, with lat/lon)"))

cells.append(code("""# UCDP Georeferenced Event Dataset for Kenya from HDX
conflict_url = ("https://data.humdata.org/dataset/1f2aa35d-6748-47f1-a07a-598294bb9c2d/"
                "resource/325d8168-f83e-43c2-a42d-5031ece08a1f/download/conflict_data_ken.csv")

cache_path = "../data/conflict_data_ken.csv"
os.makedirs("../data", exist_ok=True)

if not os.path.exists(cache_path):
    print("Downloading conflict data from HDX...")
    r = httpx.get(conflict_url, follow_redirects=True, timeout=120)
    with open(cache_path, "wb") as f:
        f.write(r.content)
    print(f"Downloaded: {len(r.content)} bytes")
else:
    print("Using cached conflict data")

conflict_df = pd.read_csv(cache_path)
print(f"Rows: {len(conflict_df)}")
print(f"Columns: {list(conflict_df.columns)}")

# Keep only relevant columns and filter to 2015-2017
conflict_df = conflict_df[(conflict_df["year"] >= 2015) & (conflict_df["year"] <= 2017)]
print(f"Filtered 2015-2017: {len(conflict_df)} events")

# Create GeoDataFrame
conflict_gdf = gpd.GeoDataFrame(
    conflict_df,
    geometry=gpd.points_from_xy(conflict_df.longitude, conflict_df.latitude),
    crs="EPSG:4326",
)
print(f"Conflict events with lat/lon: {len(conflict_gdf)}")
print(f"  Admin1 values: {conflict_gdf['adm_1'].unique()[:10]}")
"""))

# =========================================================================
# CELL 6: POPULATION DATA
# =========================================================================
cells.append(md("## 5. Download WorldPop population density (Kenya)"))

cells.append(code("""# WorldPop 100m population counts for Kenya (2020)
pop_url = "https://data.worldpop.org/GIS/Population/Global_2000_2020/2020/KEN/ken_ppp_2020.tif"
pop_cache = "../data/ken_ppp_2020.tif"

if not os.path.exists(pop_cache):
    print("Downloading WorldPop Kenya (311 MB)...")
    with httpx.Client(follow_redirects=True, timeout=300) as client:
        with client.stream("GET", pop_url) as r:
            r.raise_for_status()
            with open(pop_cache, "wb") as f:
                for chunk in r.iter_bytes(chunk_size=1<<20):
                    f.write(chunk)
    print("Download complete")
else:
    print("Using cached WorldPop data")

# Open with rasterio to verify
with rasterio.open(pop_cache) as src:
    print(f"WorldPop raster: {src.width}x{src.height}, CRS={src.crs}")
    # Read a small sample to check values
    sample = src.read(1, window=((0, 100), (0, 100)))
    print(f"  Sample shape: {sample.shape}, dtype={sample.dtype}")
    print(f"  Value range: {sample.min():.0f} - {sample.max():.0f}")
"""))

# =========================================================================
# CELL 7: DEFINE CRISIS ZONES
# =========================================================================
cells.append(code("""# Known drought crisis zones from the 2016-2017 Kenya drought
crisis_zone_names = [
    "Turkana", "Marsabit", "Mandera", "Wajir",
    "Garissa", "Tana River", "Isiolo", "Samburu"
]

admin2["adm2_name_lower"] = admin2["adm2_name"].str.lower()
crisis_mask = admin2["adm2_name_lower"].isin([n.lower() for n in crisis_zone_names])
crisis_admin2 = admin2[crisis_mask].copy()
test_admin2 = admin2[~crisis_mask].copy()

print(f"Crisis zones: {len(crisis_admin2)} — {list(crisis_admin2['adm2_name'])}")
print(f"Test zones:   {len(test_admin2)}")

# Sample 20 test zones for a balanced comparison
np.random.seed(42)
sampled_test = test_admin2.sample(min(20, len(test_admin2))).copy()
print(f"Sampled test zones: {list(sampled_test['adm2_name'])}")
"""))

# =========================================================================
# CELL 8: STAC HELPERS
# =========================================================================
cells.append(md("## 6. Sentinel-2 STAC helper functions"))

cells.append(code("""STAC_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"
COLLECTION = "sentinel-2-l2a"
BAND_KEYS = ["B02", "B03", "B04", "B08", "B11"]

def query_best_scene(polygon_geom, date_from, date_to, max_cloud=20):
    bbox = list(polygon_geom.bounds)
    catalog = StacClient.open(STAC_URL)
    search = catalog.search(
        collections=[COLLECTION],
        bbox=bbox,
        datetime=f"{date_from}/{date_to}",
        query={"eo:cloud_cover": {"lte": max_cloud}},
        max_items=20,
        sortby=[{"field": "properties.datetime", "direction": "desc"}],
    )
    items = list(search.items())
    if not items:
        return None
    for item in items:
        try:
            pc_sign(item)
        except Exception:
            pass
    items.sort(key=lambda x: (
        x.properties.get("eo:cloud_cover", 999) or 999,
        -(x.properties.get("datetime", "") or "")
    ))
    return items[0]

def get_band_url(item, band):
    asset = item.assets.get(band)
    return asset.href if asset else None

def read_band_clipped(band_url, geojson_geom, out_shape=None):
    with Reader(band_url) as reader:
        img = reader.feature(geojson_geom, out_shape=out_shape)
        band_data = img.data[0]
        return band_data, img.mask

def read_msi_stack(item, geojson_geom, target_shape=None):
    bands = {}
    first_shape = None
    for bk in BAND_KEYS:
        url = get_band_url(item, bk)
        if not url:
            print(f"  WARNING: Band {bk} not available")
            continue
        oh = target_shape
        try:
            data, mask = read_band_clipped(url, geojson_geom, out_shape=oh)
            data = np.where(mask == 0, np.nan, data)
            bands[bk] = data
            if first_shape is None:
                first_shape = data.shape
        except Exception as e:
            print(f"  ERROR reading {bk}: {e}")
            continue
    if "B11" in bands and first_shape and bands["B11"].shape != first_shape:
        bands["B11"] = resize(bands["B11"], first_shape, preserve_range=True, anti_aliasing=True)
    if not bands:
        return None
    ordered = [bands[bk] for bk in BAND_KEYS if bk in bands]
    return np.dstack(ordered)
"""))

# =========================================================================
# CELL 9: SEGMENTATION + FEATURES
# =========================================================================
cells.append(code("""def compute_indices(stack):
    b = {k: stack[:, :, i] for i, k in enumerate(BAND_KEYS) if i < stack.shape[2]}
    indices = {}
    if "B04" in b and "B08" in b:
        indices["ndvi"] = (b["B08"] - b["B04"]) / (b["B08"] + b["B04"] + 1e-10)
    if "B03" in b and "B08" in b:
        indices["ndwi"] = (b["B03"] - b["B08"]) / (b["B03"] + b["B08"] + 1e-10)
    if "B11" in b and "B08" in b:
        indices["ndbi"] = (b["B11"] - b["B08"]) / (b["B11"] + b["B08"] + 1e-10)
    indices["nir"] = b.get("B08")
    return indices


def segment_and_extract(indices_dict, n_segments=80, compactness=10):
    bands_for_seg = []
    for key in ["ndvi", "ndwi", "ndbi"]:
        arr = indices_dict.get(key)
        if arr is not None:
            lo, hi = np.nanquantile(arr, 0.02), np.nanquantile(arr, 0.98)
            norm = np.clip((arr - lo) / (hi - lo + 1e-10), 0, 1)
            bands_for_seg.append(np.nan_to_num(norm))
    if not bands_for_seg:
        return None
    seg_input = np.dstack(bands_for_seg)
    segments = slic(seg_input, n_segments=n_segments, compactness=compactness,
                    start_label=1, channel_axis=-1)

    features = []
    index_keys = list(indices_dict.keys())
    for label in np.unique(segments):
        mask = segments == label
        pixel_count = mask.sum()
        if pixel_count < 5:
            continue
        row = {"component_label": int(label), "pixel_count": pixel_count}
        for key in index_keys:
            arr = indices_dict[key]
            if arr is None:
                continue
            vals = arr[mask]
            vals = vals[~np.isnan(vals)]
            if len(vals) == 0:
                continue
            row[f"{key}_mean"] = float(np.mean(vals))
            row[f"{key}_std"] = float(np.std(vals))
        row["area_km2_approx"] = pixel_count * 0.01
        features.append(row)
    return pd.DataFrame(features)


def process_admin2_region(region_name, polygon_geom, date_from="2016-04-01",
                          date_to="2016-06-30", max_cloud=20,
                          n_segments=80, target_pixels=(500, 500)):
    item = query_best_scene(polygon_geom, date_from, date_to, max_cloud)
    if item is None:
        print(f"  {region_name}: NO SCENE FOUND")
        return None
    geojson_geom = json.loads(json.dumps(polygon_geom.__geo_interface__))
    stack = read_msi_stack(item, geojson_geom, target_shape=target_pixels)
    if stack is None:
        print(f"  {region_name}: NO BAND DATA")
        return None
    indices = compute_indices(stack)
    df = segment_and_extract(indices, n_segments=n_segments)
    if df is None or len(df) == 0:
        print(f"  {region_name}: SEGMENTATION FAILED")
        return None
    df["adm2_name"] = region_name
    df["component_centroid_lat"] = float(polygon_geom.centroid.y)
    df["component_centroid_lon"] = float(polygon_geom.centroid.x)
    print(f"  {region_name}: {len(df)} components")
    return df
"""))

# =========================================================================
# CELL 10: VECTOR FEATURE JOINS
# =========================================================================
cells.append(code("""def attach_vector_features(components_df, conflict_gdf, pop_raster_path):
    \"\"\"Spatial join: attach conflict event counts and population density to components.\"\"\"
    adm2_names = components_df["adm2_name"].unique()
    # Per admin2: count conflict events within its boundary
    # And sample population at the admin2 centroid
    
    conflict_counts = {}
    pop_values = {}
    
    for name in adm2_names:
        region = admin2[admin2["adm2_name"] == name].iloc[0]
        geom = region.geometry
        
        # Conflict events within this region
        events_in_region = conflict_gdf[conflict_gdf.intersects(geom)]
        conflict_counts[name] = len(events_in_region)
        
        # Population at centroid
        centroid = geom.centroid
        with rasterio.open(pop_raster_path) as src:
            for val in src.sample([(centroid.x, centroid.y)]):
                pop_values[name] = float(val[0])
                break
    
    components_df["conflict_events"] = components_df["adm2_name"].map(conflict_counts)
    components_df["fatalities"] = 0  # placeholder
    components_df["pop_density"] = components_df["adm2_name"].map(pop_values)
    
    # Normalize conflict count by component area
    components_df["conflict_density"] = components_df["conflict_events"] / (components_df["area_km2_approx"] + 1e-10)
    
    return components_df
"""))

# =========================================================================
# CELL 11: PROCESS CRISIS ZONES
# =========================================================================
cells.append(md("## 7. Process crisis zones → extract features"))

cells.append(code("""all_crisis_components = []
for idx, row in crisis_admin2.iterrows():
    df = process_admin2_region(row["adm2_name"], row["geometry"])
    if df is not None:
        all_crisis_components.append(df)

if all_crisis_components:
    crisis_df = pd.concat(all_crisis_components, ignore_index=True)
    print(f"\\nTotal crisis components: {len(crisis_df)}")
else:
    print("ERROR: No crisis components. Check FEWS NET data or STAC access.")
    crisis_df = pd.DataFrame()
"""))

# =========================================================================
# CELL 12: ATTACH VECTOR TO CRISIS
# =========================================================================
cells.append(code("""if len(crisis_df) > 0:
    crisis_df = attach_vector_features(crisis_df, conflict_gdf, pop_cache)
    print(f"\\nAfter vector attachment: {len(crisis_df)} components")
    print(f"Vector columns added: conflict_events, pop_density, conflict_density")
    print(crisis_df[["adm2_name", "conflict_events", "pop_density"]].head(10))
"""))

# =========================================================================
# CELL 13: CRISIS CENTROID
# =========================================================================
cells.append(code("""if crisis_df.empty:
    raise RuntimeError(
        "crisis_df is empty — no crisis components were extracted. "
        "Check STAC availability for the crisis zones or the cloud cover filter."
    )

candidate = [c for c in crisis_df.columns
             if (c.endswith("_mean") or c.endswith("_std"))
             and c != "area_km2_approx"]
extra = [c for c in ["area_km2_approx", "pixel_count",
                      "conflict_events", "pop_density", "conflict_density"]
         if c in crisis_df.columns]

crisis_feature_cols = candidate + extra

print(f"Feature columns ({len(crisis_feature_cols)}):")
for c in crisis_feature_cols:
    print(f"  {c}")

crisis_clean = crisis_df[crisis_feature_cols].dropna()
print(f"\\nClean crisis components: {len(crisis_clean)} (dropped {len(crisis_df) - len(crisis_clean)} NaN)")

if crisis_clean.empty:
    raise RuntimeError("No clean crisis components after dropping NaN.")

crisis_scaler = StandardScaler()
crisis_scaled = crisis_scaler.fit_transform(crisis_clean)
crisis_centroid = crisis_scaled.mean(axis=0).reshape(1, -1)
print(f"Crisis centroid shape: {crisis_centroid.shape}")
"""))

# =========================================================================
# CELL 14: PROCESS TEST ZONES
# =========================================================================
cells.append(md("## 8. Process test admin2 regions (same pipeline)"))

cells.append(code("""all_test_components = []
for idx, row in sampled_test.iterrows():
    df = process_admin2_region(row["adm2_name"], row["geometry"])
    if df is not None:
        all_test_components.append(df)

if all_test_components:
    test_df = pd.concat(all_test_components, ignore_index=True)
    print(f"\\nTotal test components: {len(test_df)}")
else:
    print("ERROR: No test components extracted.")
    test_df = pd.DataFrame()
"""))

# =========================================================================
# CELL 15: ATTACH VECTOR TO TEST
# =========================================================================
cells.append(code("""if len(test_df) > 0:
    test_df = attach_vector_features(test_df, conflict_gdf, pop_cache)
    print(f"\\nAfter vector attachment: {len(test_df)} components")

# Only select columns that actually exist
existing = [c for c in crisis_feature_cols if c in test_df.columns]
if len(existing) < 3:
    raise RuntimeError(f"Too few feature columns in test_df: {existing}")

test_clean = test_df[existing].dropna()
print(f"Clean test components: {len(test_clean)} (dropped {len(test_df) - len(test_clean)} NaN)")

test_clean = test_clean.copy()
test_clean["adm2_name"] = test_df.loc[test_clean.index, "adm2_name"].values
"""))

# =========================================================================
# CELL 16: SIMILARITY
# =========================================================================
cells.append(code("""test_scaled = crisis_scaler.transform(test_clean[crisis_feature_cols])
similarities = cosine_similarity(test_scaled, crisis_centroid).flatten()
test_clean["crisis_similarity"] = similarities

print(f"Similarity statistics:")
print(f"  Min:    {similarities.min():.4f}")
print(f"  Max:    {similarities.max():.4f}")
print(f"  Mean:   {similarities.mean():.4f}")
print(f"  Median: {np.median(similarities):.4f}")
"""))

# =========================================================================
# CELL 17: AGGREGATE
# =========================================================================
cells.append(code("""admin2_scores = (
    test_clean.groupby("adm2_name")
    .agg(
        mean_similarity=("crisis_similarity", "mean"),
        max_similarity=("crisis_similarity", "max"),
        n_high=("crisis_similarity", lambda x: (x > 0.7).sum()),
        n_components=("crisis_similarity", "count"),
    )
    .reset_index()
)
admin2_scores["high_ratio"] = admin2_scores["n_high"] / admin2_scores["n_components"]
admin2_scores = admin2_scores.sort_values("mean_similarity", ascending=False)

print("\\nTop 10 most crisis-resembling regions:")
print(admin2_scores.head(10)[["adm2_name", "mean_similarity", "high_ratio"]].to_string(index=False))
print("\\nBottom 10 least:")
print(admin2_scores.tail(10)[["adm2_name", "mean_similarity", "high_ratio"]].to_string(index=False))
"""))

# =========================================================================
# CELL 18: VALIDATE
# =========================================================================
cells.append(code("""# --- Validate against FEWS NET 2017 ground truth ---
url_2017 = ("https://fdw.fews.net/api/ipcphasemap/"
            "?country=KE&scenario=CS&collection_date=2017-07-01&format=geojson")

try:
    fews_2017 = gpd.read_file(url_2017)
    phase_col = [c for c in fews_2017.columns if "phase" in c.lower() or "ipc" in c.lower()]
    if not phase_col:
        raise KeyError("No IPC phase column found")
    phase_col = phase_col[0]
    crisis_2017 = fews_2017[fews_2017[phase_col] >= 3]
    print(f"FEWS NET 2017 Phase 3+ polygons: {len(crisis_2017)}")

    validation = []
    for _, row in admin2.iterrows():
        overlap = crisis_2017.intersects(row["geometry"]).any()
        validation.append({"adm2_name": row["adm2_name"],
                           "actual_crisis_2017": overlap})
    val_df = pd.DataFrame(validation)
    print(f"Regions actually in crisis (2017): {val_df['actual_crisis_2017'].sum()} / {len(val_df)}")
except Exception as e:
    print(f"FEWS NET 2017 fetch failed: {e}")
    val_df = pd.DataFrame({
        "adm2_name": admin2["adm2_name"],
        "actual_crisis_2017": admin2["adm2_name"].isin(crisis_zone_names),
    })
"""))

# =========================================================================
# CELL 19: ROC
# =========================================================================
cells.append(code("""results = admin2_scores.merge(val_df, on="adm2_name")
print(f"Validation samples: {len(results)}")

y_true = results["actual_crisis_2017"].astype(int)
y_score = results["mean_similarity"]

if len(np.unique(y_true)) > 1:
    auc = roc_auc_score(y_true, y_score)
    fpr, tpr, _ = roc_curve(y_true, y_score)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))
    ax1.plot(fpr, tpr, "b-", lw=2, label=f"AUC = {auc:.3f}")
    ax1.plot([0, 1], [0, 1], "k--", alpha=0.5)
    ax1.set_xlabel("False Positive Rate")
    ax1.set_ylabel("True Positive Rate")
    ax1.set_title("ROC Curve — Crisis Similarity Predictor")
    ax1.legend(loc="lower right")
    ax1.grid(True, alpha=0.3)

    crisis_scores = results[results["actual_crisis_2017"]]["mean_similarity"]
    non_crisis_scores = results[~results["actual_crisis_2017"]]["mean_similarity"]
    ax2.hist(crisis_scores, bins=10, alpha=0.7, label="Actual crisis (2017)", color="red")
    ax2.hist(non_crisis_scores, bins=10, alpha=0.5, label="No crisis", color="blue")
    ax2.set_xlabel("Mean similarity score")
    ax2.set_ylabel("Count")
    ax2.set_title("Score distribution by crisis status")
    ax2.legend()
    ax2.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.show()

    print(f"\\nROC AUC: {auc:.3f}")
else:
    print("Only one class — cannot compute ROC AUC")
"""))

# =========================================================================
# CELL 20: MAP
# =========================================================================
cells.append(code("""admin2_map = gpd.GeoDataFrame(
    admin2.merge(admin2_scores, on="adm2_name", how="left"), geometry="geometry")

fig, ax = plt.subplots(1, 1, figsize=(14, 12))
admin2_map.plot(
    column="mean_similarity", cmap="YlOrRd", legend=True, ax=ax,
    edgecolor="grey", linewidth=0.3,
    missing_kwds={"color": "lightgrey", "label": "No data"},
    legend_kwds={"label": "Similarity to crisis centroid", "shrink": 0.6},
)
crisis_admin2_boundary = gpd.GeoDataFrame(crisis_admin2, geometry="geometry")
crisis_admin2_boundary.boundary.plot(ax=ax, color="blue", linewidth=2, label="Known crisis (2016)")
ax.set_title("Kenya Admin2 — Semantic Similarity to Known Drought Crisis Zones", fontsize=14)
ax.legend()
ax.set_axis_off()
plt.tight_layout()
plt.show()
"""))

# =========================================================================
# CELL 21: BASELINE
# =========================================================================
cells.append(code("""# --- NDVI-only baseline ---
ndvi_only = test_clean[["ndvi_mean"]].values
crisis_ndvi_centroid = crisis_clean[["ndvi_mean"]].mean(axis=0).values.reshape(1, -1)
ndvi_scaler = StandardScaler()
ndvi_scaled = ndvi_scaler.fit_transform(ndvi_only)
ndvi_centroid_scaled = ndvi_scaler.transform(crisis_ndvi_centroid)
ndvi_sim = cosine_similarity(ndvi_scaled, ndvi_centroid_scaled).flatten()

test_clean_ndvi = test_clean.copy()
test_clean_ndvi["ndvi_similarity"] = ndvi_sim
admin2_ndvi = (
    test_clean_ndvi.groupby("adm2_name")
    .agg(mean_ndvi_sim=("ndvi_similarity", "mean"))
    .reset_index()
)
results_ndvi = admin2_ndvi.merge(val_df, on="adm2_name")
y_true = results_ndvi["actual_crisis_2017"].astype(int)
y_score_ndvi = results_ndvi["mean_ndvi_sim"]

if len(np.unique(y_true)) > 1:
    auc_ndvi = roc_auc_score(y_true, y_score_ndvi)
    print(f"ROC AUC comparison:")
    print(f"  NDVI-only:  {auc_ndvi:.3f}")
    print(f"  Fused:      {auc:.3f}")
    print(f"  Difference: {auc - auc_ndvi:+.3f}")
else:
    print("Cannot compute baseline")
"""))

# =========================================================================
# CELL 22: SUMMARY
# =========================================================================
cells.append(code("""print("=" * 95)
print(f"{'Rank':<6} {'Admin2 Region':<25} {'Mean Sim':<10} {'High%':<8} {'Crisis 2017':<12} {'Events':<8} {'Pop':<8}")
print("=" * 95)

results_sorted = results.sort_values("mean_similarity", ascending=False)
for i, (_, r) in enumerate(results_sorted.iterrows()):
    flag = "***" if r["actual_crisis_2017"] else ""
    events = test_clean[test_clean["adm2_name"] == r["adm2_name"]]["conflict_events"].iloc[0] if len(test_clean) > 0 else 0
    pop = test_clean[test_clean["adm2_name"] == r["adm2_name"]]["pop_density"].iloc[0] if len(test_clean) > 0 else 0
    print(f"{i+1:<6} {r['adm2_name']:<25} {r['mean_similarity']:<10.4f} {r['high_ratio']:<8.2%} {flag:<12} {events:<8.0f} {pop:<8.0f}")
"""))

# =========================================================================
# BUILD
# =========================================================================
nb = {
    "nbformat": 4,
    "nbformat_minor": 5,
    "metadata": {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python", "version": "3.13.0"},
    },
    "cells": cells,
}

out = os.path.join(os.path.dirname(__file__), "05_semantic_similarity_kenya.ipynb")
with open(out, "w") as f:
    json.dump(nb, f, indent=1)
print(f"Written: {out}")
print(f"Cells: {len(cells)}")
