#!/usr/bin/env python3
"""Build the functional landscape twins notebook for Kenya."""

import os, json
from pathlib import Path

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

def md(src):
    return {"cell_type": "markdown", "source": [src]}

def code(src):
    return {"cell_type": "code", "source": [src],
            "metadata": {"trusted": True}, "execution_count": None, "outputs": []}

cells = []

# =========================================================================
# CELL 1: TITLE
# =========================================================================
cells.append(md("""# 6. Functional Landscape Twins — Kenya

**Question:** Which sub-county regions outside Nairobi, Mombasa, and Kisumu are *semantically identical* to well-resourced peri-urban zones in those cities, but receive none of the same infrastructure investment?

**Method:** Segment Kenya into superpixel components via SLIC, attach spectral + proximity-based vector features, build a reference centroid from urban-fringe components within 20 km of the three largest cities, then rank every other component by cosine similarity to that centroid.

**Key insight:** Two landscape components that never appear on the same map tile can have identical functional signatures — same vegetation stress, same building density, same access to schools and health facilities. This pipeline finds those twins.
"""))

# =========================================================================
# CELL 2: GEE EXPORT
# =========================================================================
cells.append(md("""## 0. Prerequisite: Export a Kenya-wide mosaic from Google Earth Engine

Run the script below in the [GEE Code Editor](https://code.earthengine.google.com/) to export a cloud-free Sentinel-2 mosaic with vegetation and built-up indices at ~100 m resolution. Download the resulting GeoTIFF and place it at the path set in the next cell.

```javascript
// Paste into https://code.earthengine.google.com/
var geometry = ee.Geometry.Rectangle([33.5, -5.0, 42.0, 5.0]);  // Kenya bounding box

var s2 = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
  .filterBounds(geometry)
  .filterDate('2023-01-01', '2023-12-31')
  .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20))
  .median()
  .clip(geometry);

var ndvi = s2.normalizedDifference(['B8', 'B4']).rename('ndvi');
var ndbi = s2.normalizedDifference(['B11', 'B8']).rename('ndbi');
var ndwi = s2.normalizedDifference(['B3', 'B8']).rename('ndwi');

// Texture: local variance of NDVI in a 3×3 window
var texture = ndvi.reduceNeighborhood(ee.Reducer.variance(), ee.Kernel.square(1)).rename('texture');

var mosaic = ndvi.addBands(ndbi).addBands(ndwi).addBands(texture);

Export.image.toDrive({
  image: mosaic.toFloat(),
  description: 'kenya_mosaic_100m',
  scale: 100,
  crs: 'EPSG:4326',
  region: geometry,
  maxPixels: 1e10,
  fileFormat: 'GeoTIFF',
  formatOptions: {cloudOptimized: true}
});
```

After the export finishes, download `kenya_mosaic_100m.tif` and place it in the project root directory.
"""))

# =========================================================================
# CELL 3: INSTALL
# =========================================================================
cells.append(md("## 1. Install dependencies"))
cells.append(code("""import subprocess, sys
req = ["geopandas", "rasterio", "scikit-image", "scikit-learn",
       "matplotlib", "pandas", "numpy", "requests", "shapely"]
for p in req:
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", p])
"""))

# =========================================================================
# CELL 4: IMPORTS
# =========================================================================
cells.append(md("## 2. Setup"))
cells.append(code("""import json, os, sys, warnings, math
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import requests

import geopandas as gpd
import rasterio
from rasterio.mask import mask as rio_mask
from rasterio.warp import transform_bounds

from shapely.geometry import Point, box, shape
from shapely.ops import unary_union
from shapely import wkt

from skimage.segmentation import slic
from skimage.filters import sobel
from sklearn.preprocessing import StandardScaler
from sklearn.metrics.pairwise import cosine_similarity

warnings.filterwarnings("ignore")
np.set_printoptions(precision=3, suppress=True)
pd.set_option("display.max_columns", 20)

PROJECT_ROOT = Path(os.path.abspath("")).resolve()
print(f"Project root: {PROJECT_ROOT}")
"""))

# =========================================================================
# CELL 5: CONFIG
# =========================================================================
cells.append(code("""# --- Paths ---
MOSAIC_PATH = PROJECT_ROOT / "kenya_mosaic_100m.tif"
ADMIN_PATH = PROJECT_ROOT / "ken_admin2.geojson"
OUTPUT_DIR = PROJECT_ROOT / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

# --- City CBD coordinates ---
CITIES = {
    "Nairobi":  Point(36.8219, -1.2921),
    "Mombasa":  Point(39.6682, -4.0435),
    "Kisumu":   Point(34.7680, -0.0917),
}
CITY_BUFFER_KM = 20        # components within this distance are the reference set
EXCLUDE_BUFFER_KM = 30     # components within this distance are excluded from query results
N_TWINS = 50               # number of twin candidates to report

# --- Vector feature buffer radii ---
FEATURE_BUFFER_KM = 5      # for health facilities and schools

print(f"Reference cities: {list(CITIES.keys())}")
print(f"Reference buffer: {CITY_BUFFER_KM} km")
print(f"Top twins to find: {N_TWINS}")
"""))

# =========================================================================
# CELL 6: DOWNLOAD VECTOR DATA
# =========================================================================
cells.append(md("## 3. Download vector datasets from HDX"))
cells.append(code("""VECTOR_DIR = PROJECT_ROOT / "vector_data"
VECTOR_DIR.mkdir(exist_ok=True)

def _download(url, dest, label=""):
    dest = Path(dest)
    if dest.exists():
        mb = dest.stat().st_size / 1e6
        print(f"  {label or dest.name}: already cached ({mb:.0f} MB)")
        return str(dest)
    print(f"  Downloading {label or dest.name}...", end=" ", flush=True)
    try:
        r = requests.get(url, timeout=300, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        dest.write_bytes(r.content)
        mb = dest.stat().st_size / 1e6
        print(f"done ({mb:.0f} MB)")
    except Exception as e:
        print(f"FAILED: {e}")
        return None
    return str(dest)

def _unzip_to_dir(zip_path, extract_dir):
    import zipfile
    extract_dir = Path(extract_dir)
    extract_dir.mkdir(parents=True, exist_ok=True)
    if any(extract_dir.iterdir()):
        return str(extract_dir)
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(extract_dir)
    return str(extract_dir)

# --- Health facilities (OSM / HDX) ---
health_url = ("https://s3.dualstack.us-east-1.amazonaws.com/production-raw-data-api/"
              "ISO3/KEN/health_facilities/points/"
              "hotosm_ken_health_facilities_points_geojson.zip")
health_zip = _download(health_url, VECTOR_DIR / "health_facilities.zip", "Health facilities")
health_dir = _unzip_to_dir(health_zip, VECTOR_DIR / "health_facilities") if health_zip else None

# --- Schools (OSM / HDX) ---
schools_url = ("https://s3.dualstack.us-east-1.amazonaws.com/production-raw-data-api/"
               "ISO3/KEN/education_facilities/points/"
               "hotosm_ken_education_facilities_points_geojson.zip")
schools_zip = _download(schools_url, VECTOR_DIR / "schools.zip", "Schools")
schools_dir = _unzip_to_dir(schools_zip, VECTOR_DIR / "schools") if schools_zip else None

# --- Roads (HDX) ---
roads_url = ("https://data.humdata.org/dataset/3d10cb5f-f56e-4924-b1fd-32931e0ddb41/"
             "resource/0170d6b6-7ad3-439a-ae1e-e84060886502/download/kenroads.zip")
roads_zip = _download(roads_url, VECTOR_DIR / "roads.zip", "Roads")
roads_dir = _unzip_to_dir(roads_zip, VECTOR_DIR / "roads") if roads_zip else None
"""))

# =========================================================================
# CELL 7: LOAD ADMIN BOUNDARIES
# =========================================================================
cells.append(code("""if ADMIN_PATH.exists():
    admin2 = gpd.read_file(ADMIN_PATH)
    print(f"Admin2 boundaries: {len(admin2)} sub-counties")
else:
    print("WARNING: admin2 boundaries not found, creating placeholder")
    admin2 = None
"""))

# =========================================================================
# CELL 8: LOAD MOSAIC
# =========================================================================
cells.append(md("## 4. Load and verify the mosaic"))
cells.append(code("""if not MOSAIC_PATH.exists():
    raise FileNotFoundError(
        f"Mosaic not found at {MOSAIC_PATH}.\\n"
        f"Run the GEE export script in the Code Editor, download the .tif, "
        f"and place it at the path above."
    )

with rasterio.open(MOSAIC_PATH) as src:
    mosaic_meta = src.meta.copy()
    mosaic_bands = src.descriptions
    mosaic_shape = (src.height, src.width)
    print(f"Mosaic: {mosaic_shape[0]}×{mosaic_shape[1]} pixels")
    print(f"CRS: {src.crs}")
    print(f"Bands ({src.count}): {[d or f'Band {i+1}' for i, d in enumerate(src.descriptions)]}")
    print(f"Bounds: {src.bounds}")
"""))

# =========================================================================
# CELL 9: SLIC SEGMENTATION
# =========================================================================
cells.append(md("## 5. Segment the mosaic into components"))
cells.append(code("""with rasterio.open(MOSAIC_PATH) as src:
    mosaic_data = src.read()
    mosaic_profile = src.profile

# mosaic_data shape: (bands, H, W) → transpose to (H, W, bands)
img = np.moveaxis(mosaic_data, 0, -1)
H, W, C = img.shape
print(f"Array shape: {H}×{W}×{C}")

# Normalize each band to [0,1] for SLIC
seg_input = np.zeros_like(img)
for c in range(C):
    band = img[:, :, c]
    lo, hi = np.nanquantile(band, 0.02), np.nanquantile(band, 0.98)
    seg_input[:, :, c] = np.nan_to_num(np.clip((band - lo) / (hi - lo + 1e-10), 0, 1))

# Run SLIC
N_SEGMENTS = 3000
COMPACTNESS = 10
print(f"Running SLIC (n_segments={N_SEGMENTS}, compactness={COMPACTNESS})...", flush=True)
segments = slic(seg_input, n_segments=N_SEGMENTS, compactness=COMPACTNESS,
                start_label=1, channel_axis=-1)
n_components = len(np.unique(segments))
print(f"Segments found: {n_components}")
"""))

# =========================================================================
# CELL 10: EXTRACT SPECTRAL FEATURES
# =========================================================================
cells.append(md("## 6. Extract per-component features"))
cells.append(code("""BAND_NAMES = [d or f"Band_{i}" for i, d in enumerate(mosaic_bands)]

def extract_spectral_features(img, segments):
    features = []
    for label in np.unique(segments):
        mask = (segments == label)
        px = mask.sum()
        if px < 5:
            continue
        row = {"component_id": int(label), "pixel_count": int(px)}
        for c in range(C):
            vals = img[:, :, c][mask]
            vals = vals[~np.isnan(vals)]
            if len(vals) == 0:
                continue
            row[f"{BAND_NAMES[c]}_mean"] = float(np.mean(vals))
            row[f"{BAND_NAMES[c]}_std"] = float(np.std(vals))
        row["area_km2"] = px * 0.01
        features.append(row)
    return pd.DataFrame(features)

components = extract_spectral_features(img, segments)
print(f"Components with features: {len(components)}")

# --- Assign each component to its nearest admin2 ---
# Compute component centroids in pixel coords, then georeference
def component_geometries(segments, profile):
    transform = profile["transform"]
    geoms = {}
    for label in np.unique(segments):
        mask = (segments == label)
        if mask.sum() < 5:
            continue
        ys, xs = np.where(mask)
        lons, lats = rasterio.transform.xy(transform, ys, xs, offset="center")
        centroid_lon = np.mean(lons)
        centroid_lat = np.mean(lats)
        geoms[int(label)] = Point(centroid_lon, centroid_lat)
    return gpd.GeoDataFrame(
        {"component_id": list(geoms.keys())},
        geometry=list(geoms.values()),
        crs="EPSG:4326",
    )

comp_geo = component_geometries(segments, mosaic_profile)
print(f"Component geometries: {len(comp_geo)}")

# Spatial join with admin2
if admin2 is not None:
    comp_geo = gpd.sjoin(comp_geo, admin2[["adm2_name", "adm1_name", "geometry"]],
                         how="left", predicate="within")
    comp_geo.drop(columns="index_right", errors="ignore", inplace=True)
    nan_adm = comp_geo["adm2_name"].isna().sum()
    if nan_adm:
        print(f"WARNING: {nan_adm} components fall outside admin boundaries")
    # Merge back into components df
    components = components.merge(
        comp_geo[["component_id", "adm2_name", "adm1_name"]],
        on="component_id", how="left"
    )
else:
    components["adm2_name"] = "unknown"
    components["adm1_name"] = "unknown"

print(f"Components after admin join: {len(components)}")
"""))

# =========================================================================
# CELL 11: ATTACH POPULATION DENSITY
# =========================================================================
cells.append(md("## 7. Attach vector features"))
cells.append(code("""# --- WorldPop ---
POP_PATH = VECTOR_DIR / "ken_ppp_2020_constrained.tif"
if not POP_PATH.exists():
    pop_url = "https://data.worldpop.org/GIS/Population/Global_2000_2020/2020/KEN/ken_ppp_2020_constrained.tif"
    print("Downloading WorldPop...", flush=True)
    try:
        r = requests.get(pop_url, timeout=300, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        POP_PATH.write_bytes(r.content)
        print(f"  done ({POP_PATH.stat().st_size >> 20} MB)")
    except Exception as e:
        print(f"  FAILED: {e}")

def sample_raster_at_points(points_gdf, raster_path, col_name="pop_density"):
    values = np.full(len(points_gdf), np.nan)
    try:
        with rasterio.open(raster_path) as src:
            coords = [(pt.x, pt.y) for pt in points_gdf.geometry]
            samples = list(src.sample(coords))
            values = np.array([s[0] for s in samples]).astype(float)
            values[values < 0] = np.nan
    except Exception as e:
        print(f"  WARNING: pop sampling failed: {e}")
    return values

pop_vals = sample_raster_at_points(comp_geo, POP_PATH, "pop_density")
comp_geo["pop_density"] = pop_vals
components = components.merge(comp_geo[["component_id", "pop_density"]], on="component_id", how="left")
print(f"Pop density attached: {np.isfinite(pop_vals).sum()} / {len(pop_vals)} have values")
"""))

# =========================================================================
# CELL 12: SPATIAL JOIN — HEALTH FACILITIES
# =========================================================================
cells.append(code("""def _load_osm_dir(dir_path):
    if not dir_path or not os.path.isdir(dir_path):
        return None
    for f in os.listdir(dir_path):
        if f.endswith(".geojson"):
            return gpd.read_file(os.path.join(dir_path, f))
    # Fallback: try reading the directory as a shapefile
    shp_files = [f for f in os.listdir(dir_path) if f.endswith(".shp")]
    if shp_files:
        return gpd.read_file(os.path.join(dir_path, shp_files[0]))
    return None

def count_nearby(points_gdf, data_dir, buffer_km=5, col_name="features"):
    counts = np.zeros(len(points_gdf), dtype=int)
    feats = _load_osm_dir(data_dir)
    if feats is None or len(feats) == 0:
        print(f"  {col_name}: no data loaded")
        return counts
    try:
        if feats.crs is None or feats.crs != "EPSG:4326":
            feats.set_crs("EPSG:4326", inplace=True)
        feats_sindex = feats.sindex
        buffer_deg = buffer_km / 111.0
        for i, pt in enumerate(points_gdf.geometry):
            bounds = (pt.x - buffer_deg, pt.y - buffer_deg,
                      pt.x + buffer_deg, pt.y + buffer_deg)
            candidates = feats.iloc[list(feats_sindex.intersection(bounds))]
            if len(candidates) == 0:
                continue
            distances = candidates.distance(pt)
            counts[i] = int((distances <= buffer_deg).sum())
        print(f"  {col_name}: max={counts.max()}, mean={counts.mean():.1f}")
    except Exception as e:
        print(f"  {col_name}: FAILED ({e})")
    return counts

comp_geo["health_facilities"] = count_nearby(comp_geo, health_dir, FEATURE_BUFFER_KM, "Health facilities")
"""))

# =========================================================================
# CELL 13: SPATIAL JOIN — SCHOOLS
# =========================================================================
cells.append(code("""comp_geo["schools"] = count_nearby(comp_geo, schools_dir, FEATURE_BUFFER_KM, "Schools")
"""))

# =========================================================================
# CELL 14: ROAD DENSITY
# =========================================================================
cells.append(code("""def road_density(points_gdf, road_dir, buffer_km=2):
    densities = np.zeros(len(points_gdf))
    roads = _load_osm_dir(road_dir)
    if roads is None or len(roads) == 0:
        print("  SKIP: roads not available")
        return densities
    try:
        if roads.crs is None:
            roads.set_crs("EPSG:4326", inplace=True)
        roads_proj = roads.to_crs("EPSG:3857")
        roads_sindex = roads_proj.sindex
        buffer_m = buffer_km * 1000
        for i, pt in enumerate(points_gdf.geometry):
            pt_proj = gpd.GeoSeries([pt], crs="EPSG:4326").to_crs("EPSG:3857").iloc[0]
            bounds = (pt_proj.x - buffer_m, pt_proj.y - buffer_m,
                      pt_proj.x + buffer_m, pt_proj.y + buffer_m)
            candidates = roads_proj.iloc[list(roads_sindex.intersection(bounds))]
            if len(candidates) == 0:
                continue
            circle = pt_proj.buffer(buffer_m)
            clipped = candidates.intersection(circle)
            total_km = clipped.length.sum() / 1000
            densities[i] = total_km / (math.pi * (buffer_km ** 2))
        print(f"  Road density: max={densities.max():.2f} km/km2, mean={densities.mean():.2f}")
    except Exception as e:
        print(f"  Road density FAILED: {e}")
    return densities

comp_geo["road_density"] = road_density(comp_geo, roads_dir, buffer_km=2)
"""))

# =========================================================================
# CELL 15: MERGE ALL FEATURES
# =========================================================================
cells.append(code("""# Merge all vector features into components
vector_cols = ["pop_density", "health_facilities", "schools", "road_density"]
components = components.merge(
    comp_geo[["component_id"] + vector_cols], on="component_id", how="left"
)

# Fill NaN
for c in vector_cols:
    components[c] = components[c].fillna(0)

print(f"Final component table: {len(components)} rows, {len(components.columns)} columns")
print("Columns:", list(components.columns))
print(components[["component_id", "adm2_name", "pop_density", "health_facilities", "schools", "road_density"]].head(10))
"""))

# =========================================================================
# CELL 16: BUILD FEATURE MATRIX
# =========================================================================
cells.append(md("## 8. Compute similarity matrix"))
cells.append(code("""# Feature columns: spectral means/stds + vector features
feat_cols = [c for c in components.columns
             if c.endswith("_mean") or c.endswith("_std")]
feat_cols += vector_cols
print(f"Feature columns ({len(feat_cols)}):")
for c in feat_cols:
    print(f"  {c}")

# Drop NaN rows
clean = components[feat_cols].dropna()
print(f"Clean components: {len(clean)} / {len(components)}")
clean_idx = clean.index.values

# Normalize
scaler = StandardScaler()
X = scaler.fit_transform(clean)
print(f"Feature matrix shape: {X.shape}")

# Full similarity matrix: S = X @ X.T
print("Computing similarity matrix (X @ X.T)...", flush=True)
S = X @ X.T
print(f"Similarity matrix shape: {S.shape}")
print(f"Similarity range: [{S.min():.4f}, {S.max():.4f}]")
"""))

# =========================================================================
# CELL 17: DEFINE REFERENCE SET
# =========================================================================
cells.append(code("""# --- Reference: components within CITY_BUFFER_KM of a city CBD ---
comp_geo_clean = comp_geo.loc[clean_idx].copy()
buffer_deg = CITY_BUFFER_KM / 111.0

is_reference = np.zeros(len(comp_geo_clean), dtype=bool)
for city_name, city_pt in CITIES.items():
    mask = comp_geo_clean.distance(city_pt) <= buffer_deg
    is_reference |= mask.values
    n = mask.sum()
    if n:
        print(f"  {city_name}: {n} reference components")

ref_idx = np.where(is_reference)[0]
print(f"Total reference components: {len(ref_idx)}")

if len(ref_idx) < 3:
    raise RuntimeError(f"Too few reference components ({len(ref_idx)}). "
                       f"The mosaic may not cover the city areas. Check the GEE export.")
"""))

# =========================================================================
# CELL 18: CENTROID COSINE SIMILARITY
# =========================================================================
cells.append(code("""# --- Reference centroid ---
ref_centroid = X[ref_idx].mean(axis=0)

# Cosine similarity of every component to the reference centroid
target = ref_centroid.reshape(1, -1)
similarities = cosine_similarity(X, target).flatten()

results = pd.DataFrame({
    "component_id": components.loc[clean_idx, "component_id"].values,
    "adm2_name": components.loc[clean_idx, "adm2_name"].values,
    "adm1_name": components.loc[clean_idx, "adm1_name"].values,
    "similarity": similarities,
    "pop_density": components.loc[clean_idx, "pop_density"].values,
    "health_facilities": components.loc[clean_idx, "health_facilities"].values,
    "schools": components.loc[clean_idx, "schools"].values,
    "road_density": components.loc[clean_idx, "road_density"].values,
})
results["is_reference"] = is_reference

# --- Exclude reference components and those within EXCLUDE_BUFFER_KM ---
exclude_deg = EXCLUDE_BUFFER_KM / 111.0
is_near_city = np.zeros(len(comp_geo_clean), dtype=bool)
for city_pt in CITIES.values():
    is_near_city |= (comp_geo_clean.distance(city_pt) <= exclude_deg).values

results["is_near_city"] = is_near_city
query = results[~results["is_reference"] & ~results["is_near_city"]].copy()

print(f"Query set: {len(query)} components (excluded {results['is_reference'].sum()} reference + "
      f"{(results['is_near_city'] & ~results['is_reference']).sum()} city-buffer)")
print(f"Similarity range in query: [{query['similarity'].min():.4f}, {query['similarity'].max():.4f}]")
"""))

# =========================================================================
# CELL 19: TOP TWINS
# =========================================================================
cells.append(md("## 9. Top 50 functional landscape twins"))
cells.append(code("""top = query.sort_values("similarity", ascending=False).head(N_TWINS).copy()
top["rank"] = range(1, len(top) + 1)

print(f"{'Rank':<6} {'Adm2':<25} {'County':<18} {'Similarity':<11} {'Pop/km²':<9} {'Health':<8} {'Schools':<8} {'Road km/km²':<12}")
print("=" * 100)
for _, r in top.iterrows():
    print(f"{r['rank']:<6} {r['adm2_name']:<25} {r['adm1_name']:<18} "
          f"{r['similarity']:<11.4f} {r['pop_density']:<9.1f} "
          f"{r['health_facilities']:<8} {r['schools']:<8} {r['road_density']:<12.2f}")

print(f"\\n--- Top twins by county ---")
print(top["adm1_name"].value_counts().head(10).to_string())

# Save to CSV
top.to_csv(OUTPUT_DIR / "functional_twins_top50.csv", index=False)
print(f"\\nSaved to {OUTPUT_DIR / 'functional_twins_top50.csv'}")
"""))

# =========================================================================
# CELL 20: MAP
# =========================================================================
cells.append(md("## 10. Map"))
cells.append(code("""if admin2 is not None:
    # Aggregate twin count per admin2
    twin_counts = top.groupby("adm2_name").size().reset_index(name="twin_components")
    admin2_map = admin2.merge(twin_counts, on="adm2_name", how="left")
    admin2_map["twin_components"] = admin2_map["twin_components"].fillna(0).astype(int)

    fig, ax = plt.subplots(1, 1, figsize=(14, 12))

    admin2_map.plot(
        column="twin_components", cmap="YlOrRd", edgecolor="grey",
        linewidth=0.3, legend=True, ax=ax,
        legend_kwds={"label": "Twin components", "shrink": 0.6},
    )

    # Mark city buffers
    from shapely.geometry import Point
    for city_name, city_pt in CITIES.items():
        circle = city_pt.buffer(EXCLUDE_BUFFER_KM / 111.0)
        gpd.GeoSeries([circle], crs="EPSG:4326").boundary.plot(
            ax=ax, color="blue", linewidth=1.5, linestyle="--",
            label=f"{city_name} ({EXCLUDE_BUFFER_KM}km)" if city_name == "Nairobi" else "")

    # Plot top twin component centroids
    twin_geo = comp_geo_clean.loc[results["component_id"].isin(top["component_id"])]
    if len(twin_geo):
        twin_geo = twin_geo.to_crs("EPSG:4326")
        twin_geo.plot(ax=ax, color="cyan", markersize=15, marker="*",
                      edgecolor="black", linewidth=0.5, label="Top 50 twins")

    ax.set_title("Kenya — Functional Landscape Twins of Urban-Fringe Zones", fontsize=14)
    ax.legend(fontsize=9, loc="lower left")
    ax.set_axis_off()
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "functional_twins_map.png", dpi=150, bbox_inches="tight")
    plt.show()
    print(f"Map saved to {OUTPUT_DIR / 'functional_twins_map.png'}")
else:
    print("Admin2 boundaries not available — cannot generate map.")
"""))

# =========================================================================
# CELL 21: SUMMARY
# =========================================================================
cells.append(md("## 11. Interpretation"))
cells.append(code("""print("=" * 70)
print("FUNCTIONAL LANDSCAPE TWINS — SUMMARY")
print("=" * 70)
print(f"\\nReference set: {len(ref_idx)} components within {CITY_BUFFER_KM} km of "
      f"{', '.join(CITIES.keys())}")
print(f"Query set:     {len(query)} components outside city exclusion zones")
print(f"Top twins:     {N_TWINS} components with highest cosine similarity to reference centroid")
print()

# Which counties are over-represented?
top_counties = top.groupby("adm1_name").agg(
    n_twins=("component_id", "count"),
    avg_similarity=("similarity", "mean")
).sort_values("n_twins", ascending=False)

print("Counties with most twin components:")
for county, row in top_counties.iterrows():
    print(f"  {county:<20} {row['n_twins']:>3} twins  (avg similarity: {row['avg_similarity']:.4f})")

print(f"\\nTop 3 twin regions:")
for _, r in top.head(3).iterrows():
    print(f"  {r['rank']}. {r['adm2_name']}, {r['adm1_name']} "
          f"(sim={r['similarity']:.4f}, pop={r['pop_density']:.0f}/km², "
          f"{r['health_facilities']} health, {r['schools']} schools)")

print("\\nNext step: Load the CSV and investigate specific twin regions for")
print("policy-relevant insights about infrastructure misallocation.")
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

out = os.path.join(os.path.dirname(__file__), "06_functional_twins_kenya.ipynb")
with open(out, "w") as f:
    json.dump(nb, f, indent=1)
print(f"Written: {out}")
print(f"Cells: {len(cells)}")
