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
# CELL 2: STAC MOSAIC
# =========================================================================
cells.append(md("""## 0. Build a Kenya-wide mosaic from Planetary Computer STAC

This notebook queries the [Planetary Computer STAC API](https://planetarycomputer.microsoft.com/) for cloud-free Sentinel-2 L2A scenes covering Kenya, then processes each scene individually at ~100 m resolution — segmenting, extracting features, and attaching vector data — finally combining all components into a national similarity analysis.

No external exports are needed. The first run downloads and caches all data locally.
"""))

# =========================================================================
# CELL 3: INSTALL
# =========================================================================
cells.append(md("## 1. Install dependencies"))
cells.append(code("""import subprocess, sys
req = ["geopandas", "pyarrow", "rasterio", "scikit-image", "scikit-learn",
       "matplotlib", "pandas", "numpy", "requests", "shapely",
       "pystac-client", "planetary-computer"]
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

import pystac_client
from planetary_computer import sign as pc_sign

from skimage.segmentation import slic
from skimage.filters import sobel
from sklearn.preprocessing import StandardScaler
from sklearn.metrics.pairwise import cosine_similarity

warnings.filterwarnings("ignore")
np.set_printoptions(precision=3, suppress=True)
pd.set_option("display.max_columns", 20)

_cwd = Path(os.path.abspath("")).resolve()
# Try parent dir if ken_admin2.geojson is there (codespace root)
if (_cwd.parent / "ken_admin2.geojson").exists():
    PROJECT_ROOT = _cwd.parent
else:
    PROJECT_ROOT = _cwd
print(f"Project root: {PROJECT_ROOT}")
print(f"Admin path:  {PROJECT_ROOT / 'ken_admin2.geojson'} exists={(PROJECT_ROOT / 'ken_admin2.geojson').exists()}")
"""))

# =========================================================================
# CELL 5: CONFIG
# =========================================================================
cells.append(code("""# --- Paths ---
ADMIN_PATH = PROJECT_ROOT / "ken_admin2.geojson"
OUTPUT_DIR = PROJECT_ROOT / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

# --- STAC query parameters ---
KENYA_BBOX = [33.5, -5.0, 42.0, 5.0]
DATE_RANGE = "2023-01-01/2023-12-31"
MAX_CLOUD = 20
MAX_SCENES = 60

# --- City CBD coordinates ---
CITIES = {
    "Nairobi":  Point(36.8219, -1.2921),
    "Mombasa":  Point(39.6682, -4.0435),
    "Kisumu":   Point(34.7680, -0.0917),
}
CITY_BUFFER_KM = 20
EXCLUDE_BUFFER_KM = 30
N_TWINS = 50
FEATURE_BUFFER_KM = 5      # for health facilities and schools

print(f"Reference cities: {list(CITIES.keys())}")
print(f"Mosaic: STAC query in Kenya bbox, {DATE_RANGE}, cloud < {MAX_CLOUD}%")
print(f"Target resolution: {TARGET_RES_M} m")
print(f"Top twins to find: {N_TWINS}")
"""))

# =========================================================================
# CELL 6: DOWNLOAD VECTOR DATA
# =========================================================================
cells.append(md("## 3. Download vector datasets from HDX"))
cells.append(code("""VECTOR_DIR = PROJECT_ROOT / "vector_data"
VECTOR_DIR.mkdir(exist_ok=True)

def _fmt_sz(bs):
    if bs > 1e6:
        return f"{bs/1e6:.1f} MB"
    return f"{bs/1e3:.0f} KB"

def _download(url, dest, label=""):
    dest = Path(dest)
    if dest.exists():
        sz = dest.stat().st_size
        print(f"  {label or dest.name}: already cached ({_fmt_sz(sz)})")
        return str(dest)
    print(f"  Downloading {label or dest.name}...", end=" ", flush=True)
    try:
        r = requests.get(url, timeout=300, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        dest.write_bytes(r.content)
        print(f"done ({_fmt_sz(dest.stat().st_size)})")
    except Exception as e:
        print(f"FAILED: {e}")
        return None
    return str(dest)

def _ensure_parquet(zip_url, zip_name, parquet_name, label=""):
    # Download ZIP, extract, convert to GeoParquet. Subsequent runs load parquet directly.
    parquet_path = VECTOR_DIR / parquet_name
    if parquet_path.exists():
        print(f"  {label or parquet_name}: loaded from parquet ({_fmt_sz(parquet_path.stat().st_size)})")
        return str(parquet_path)

    zip_path = VECTOR_DIR / zip_name
    if not zip_path.exists():
        _download(zip_url, zip_path, label)
        if not zip_path.exists():
            return None

    import zipfile, tempfile
    with tempfile.TemporaryDirectory() as tmp:
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(tmp)
        vec_file = None
        for root, _dirs, files in os.walk(tmp):
            for f in files:
                if f.endswith((".geojson", ".shp", ".gpkg")):
                    vec_file = os.path.join(root, f)
                    break
            if vec_file:
                break
        if vec_file is None:
            print(f"  {label}: no vector file found in ZIP")
            return None
        gdf = gpd.read_file(vec_file)
        if gdf.crs is None:
            gdf.set_crs("EPSG:4326", inplace=True)
        gdf.to_parquet(parquet_path)
    print(f"  {label}: converted to GeoParquet ({_fmt_sz(parquet_path.stat().st_size)})")
    return str(parquet_path)

# --- Health facilities ---
health_path = _ensure_parquet(
    "https://s3.dualstack.us-east-1.amazonaws.com/production-raw-data-api/"
    "ISO3/KEN/health_facilities/points/hotosm_ken_health_facilities_points_geojson.zip",
    "health_facilities.zip", "health_facilities.parquet", "Health facilities")

# --- Schools ---
schools_path = _ensure_parquet(
    "https://s3.dualstack.us-east-1.amazonaws.com/production-raw-data-api/"
    "ISO3/KEN/education_facilities/points/hotosm_ken_education_facilities_points_geojson.zip",
    "schools.zip", "schools.parquet", "Schools")

# --- Roads ---
roads_path = _ensure_parquet(
    "https://data.humdata.org/dataset/3d10cb5f-f56e-4924-b1fd-32931e0ddb41/"
    "resource/0170d6b6-7ad3-439a-ae1e-e84060886502/download/kenroads.zip",
    "roads.zip", "roads.parquet", "Roads")
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
# CELL 8: STAC PER-TILE PROCESSING
# =========================================================================
cells.append(md("## 4. Process each Sentinel-2 scene from Planetary Computer"))
cells.append(code("""BAND_NAMES = ["ndvi", "ndbi", "ndwi"]

def _read_at_res(href, target_pixels=1000):
    with rasterio.open(href) as src:
        oh, ow = src.height, src.width
        if oh >= ow:
            h, w = target_pixels, max(1, int(ow * target_pixels / oh))
        else:
            w, h = target_pixels, max(1, int(oh * target_pixels / ow))
        data = src.read(out_shape=(1, h, w)).astype(np.float32)
        new_tfm = rasterio.transform.from_bounds(
            src.bounds.left, src.bounds.bottom,
            src.bounds.right, src.bounds.top, w, h)
        return data[0], new_tfm

def process_stac_tile(item, admin_gdf, health_gdf, schools_gdf, roads_gdf, pop_src):
    from planetary_computer import sign
    signed = sign(item)

    # Read bands at reduced resolution (~1000×1000)
    b04, _ = _read_at_res(signed.assets["B04"].href)
    b03, _ = _read_at_res(signed.assets["B03"].href)
    b08, _ = _read_at_res(signed.assets["B08"].href)
    b11, src_tfm = _read_at_res(signed.assets["B11"].href)
    # Get CRS from the raster itself (reliable)
    with rasterio.open(signed.assets["B04"].href) as _src:
        tile_crs = _src.crs
    s2 = np.dstack([np.nan_to_num(b04.astype(float)),
                    np.nan_to_num(b03.astype(float)),
                    np.nan_to_num(b08.astype(float)),
                    np.nan_to_num(b11.astype(float))])

    ndvi = (s2[:, :, 2] - s2[:, :, 0]) / (s2[:, :, 2] + s2[:, :, 0] + 1e-10)
    ndbi = (s2[:, :, 3] - s2[:, :, 2]) / (s2[:, :, 3] + s2[:, :, 2] + 1e-10)
    ndwi = (s2[:, :, 1] - s2[:, :, 2]) / (s2[:, :, 1] + s2[:, :, 2] + 1e-10)

    seg_stack = np.dstack([ndvi, ndbi, ndwi])
    seg_input = np.zeros_like(seg_stack)
    for c in range(3):
        band = seg_stack[:, :, c]
        lo, hi = np.nanquantile(band, 0.02), np.nanquantile(band, 0.98)
        seg_input[:, :, c] = np.clip((band - lo) / (hi - lo + 1e-10), 0, 1)

    n_seg = max(20, (seg_stack.shape[0] * seg_stack.shape[1]) // 15000)
    segs = slic(seg_input, n_segments=n_seg, compactness=10, start_label=1, channel_axis=-1)

    rows = []
    geo_rows = []
    for label in np.unique(segs):
        mask = (segs == label)
        px = mask.sum()
        if px < 5:
            continue
        cid = int(f"{item.id[-6:]}{label:04d}")
        r = {"component_id": cid, "pixel_count": px, "scene_id": item.id}
        for i, name in enumerate(BAND_NAMES):
            vals = seg_stack[:, :, i][mask]
            vals = vals[np.isfinite(vals)]
            if len(vals):
                r[f"{name}_mean"] = float(np.mean(vals))
                r[f"{name}_std"] = float(np.std(vals))
        r["area_km2"] = px * (abs(src_tfm[0]) ** 2) / 1e6
        rows.append(r)

        ys, xs = np.where(mask)
        lons, lats = rasterio.transform.xy(src_tfm, ys, xs, offset="center")
        geo_rows.append({"component_id": cid,
                         "geometry": Point(float(np.mean(lons)), float(np.mean(lats)))})

    df = pd.DataFrame(rows)
    geo = gpd.GeoDataFrame(geo_rows, crs=tile_crs)
    # Transform to WGS84 for spatial joins (always, to be safe)
    geo = geo.to_crs("EPSG:4326")

    # Admin join
    if admin_gdf is not None:
        geo = gpd.sjoin(geo, admin_gdf[["adm2_name", "adm1_name", "geometry"]],
                        how="left", predicate="within")
        geo.drop(columns="index_right", errors="ignore", inplace=True)
    else:
        geo["adm2_name"] = "unknown"
        geo["adm1_name"] = "unknown"
    df = df.merge(geo[["component_id", "adm2_name", "adm1_name"]], on="component_id")

    # Vector feature joins
    def _cnt(gdf_col):
        if gdf_col is None:
            return np.zeros(len(geo))
        bdeg = FEATURE_BUFFER_KM / 111.0
        cnt = np.zeros(len(geo), dtype=int)
        try:
            sidx = gdf_col.sindex
            for i, pt in enumerate(geo.geometry):
                b = (pt.x - bdeg, pt.y - bdeg, pt.x + bdeg, pt.y + bdeg)
                cands = gdf_col.iloc[list(sidx.intersection(b))]
                if len(cands):
                    cnt[i] = int((cands.distance(pt) <= bdeg).sum())
        except Exception:
            pass
        return cnt

    df["health_facilities"] = _cnt(health_gdf)
    df["schools"] = _cnt(schools_gdf)

    # Road density
    road_dens = np.zeros(len(geo))
    if roads_gdf is not None:
        try:
            rproj = roads_gdf.to_crs("EPSG:3857")
            r_idx = rproj.sindex
            bm = 2000
            for i, pt in enumerate(geo.geometry):
                p = gpd.GeoSeries([pt], crs="EPSG:4326").to_crs("EPSG:3857").iloc[0]
                b = (p.x - bm, p.y - bm, p.x + bm, p.y + bm)
                cands = rproj.iloc[list(r_idx.intersection(b))]
                if len(cands):
                    clipped = cands.intersection(p.buffer(bm))
                    road_dens[i] = clipped.length.sum() / 1000 / (math.pi * 4)
        except Exception:
            pass
    df["road_density"] = road_dens

    # Pop density
    pop = np.full(len(geo), np.nan)
    if pop_src is not None:
        try:
            coords = [(pt.x, pt.y) for pt in geo.geometry]
            samples = list(pop_src.sample(coords))
            pop = np.array([s[0] for s in samples]).astype(float)
            pop[pop < 0] = np.nan
        except Exception:
            pass
    df["pop_density"] = pop

    return df, geo

# --- Load vector features into memory ---
def _load_parquet(path):
    if path and os.path.exists(path):
        try:
            return gpd.read_parquet(path)
        except Exception:
            pass
    return None

health_gdf = _load_parquet(health_path)
schools_gdf = _load_parquet(schools_path)
roads_gdf = _load_parquet(roads_path)

POP_PATH = VECTOR_DIR / "ken_ppp_2020.tif"
if not POP_PATH.exists():
    pop_url = "https://data.worldpop.org/GIS/Population/Global_2000_2020/2020/KEN/ken_ppp_2020.tif"
    print("Downloading WorldPop...", flush=True)
    try:
        r = requests.get(pop_url, timeout=300, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        POP_PATH.write_bytes(r.content)
    except Exception as e:
        print(f"  FAILED: {e}")
pop_src = rasterio.open(POP_PATH) if POP_PATH.exists() else None

for label, gdf in [("Health", health_gdf), ("Schools", schools_gdf), ("Roads", roads_gdf),
                   ("Pop", pop_src)]:
    status = "loaded" if (gdf is not None) else "unavailable"
    print(f"  {label}: {status}")

# --- Query STAC ---
import pystac_client
from planetary_computer import sign as pc_sign

catalog = pystac_client.Client.open(
    "https://planetarycomputer.microsoft.com/api/stac/v1",
    modifier=pc_sign)
search = catalog.search(
    collections=["sentinel-2-l2a"],
    bbox=KENYA_BBOX,
    datetime=DATE_RANGE,
    query={"eo:cloud_cover": {"lt": MAX_CLOUD}},
)
items = sorted(search.items(), key=lambda i: i.properties.get("eo:cloud_cover", 100))
print(f"STAC items found: {len(items)}")

if len(items) > MAX_SCENES:
    items = items[:MAX_SCENES]
    print(f"  Using top {MAX_SCENES} by cloud cover")

# --- Process each scene ---
all_components = []
all_geo = []

for idx, item in enumerate(items):
    item_id = item.id
    cc = item.properties.get("eo:cloud_cover", -1)
    bbox = item.bbox
    cx, cy = (bbox[0]+bbox[2])/2, (bbox[1]+bbox[3])/2
    print(f"[{idx+1}/{len(items)}] {item_id} cc={cc}% at ({cx:.1f},{cy:.1f})...", end=" ", flush=True)
    # Check if near any city
    for cname, cpt in CITIES.items():
        if abs(cx - cpt.x) < 2 and abs(cy - cpt.y) < 2:
            print(f"(covers {cname}) ", end="")
            break
    try:
        df, geo = process_stac_tile(item, admin2, health_gdf, schools_gdf, roads_gdf, pop_src)
        all_components.append(df)
        all_geo.append(geo)
        print(f"{len(df)} components")
    except Exception as e:
        print(f"FAILED: {e}")

if pop_src is not None:
    pop_src.close()

components = pd.concat(all_components, ignore_index=True) if all_components else pd.DataFrame()
comp_geo = pd.concat(all_geo, ignore_index=True) if all_geo else gpd.GeoDataFrame()

print(f"\\nTotal components: {len(components)}")
print(f"Columns: {list(components.columns)}")

VECTOR_COLS = ["pop_density", "health_facilities", "schools", "road_density"]
for c in VECTOR_COLS:
    if c in components.columns:
        components[c] = components[c].fillna(0)
"""))

# =========================================================================
# CELL 16: BUILD FEATURE MATRIX
# =========================================================================
cells.append(md("## 8. Compute similarity matrix"))
cells.append(code("""# Feature columns: spectral means/stds + vector features
feat_cols = [c for c in components.columns
             if c.endswith("_mean") or c.endswith("_std")]
feat_cols += VECTOR_COLS
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
buffer_deg = CITY_BUFFER_KM / 111.0

# Look up geometry for each clean component by component_id
geo_map = comp_geo.set_index("component_id")["geometry"]
clean_cids = components.loc[clean_idx, "component_id"].values
clean_geoms = geo_map.loc[clean_cids]

print(f"Clean components: {len(clean_geoms)} (total components: {len(components)})")
print(f"Geo range: lon=[{clean_geoms.x.min():.2f}, {clean_geoms.x.max():.2f}], "
      f"lat=[{clean_geoms.y.min():.2f}, {clean_geoms.y.max():.2f}]")

is_reference = np.zeros(len(clean_geoms), dtype=bool)
for city_name, city_pt in CITIES.items():
    dists = clean_geoms.distance(city_pt) * 111  # approximate km
    mask = dists <= CITY_BUFFER_KM
    is_reference |= mask.values
    n = int(mask.sum())
    if n:
        print(f"  {city_name}: {n} reference components (within {CITY_BUFFER_KM} km)")
    else:
        print(f"  {city_name}: 0 in buffer (min distance = {dists.min():.1f} km)")

ref_idx = np.where(is_reference)[0]
print(f"Total reference components: {len(ref_idx)}")

if len(ref_idx) < 3:
    print(f"\\nSample component locations (first 10):")
    for cid, geom in list(zip(clean_cids[:10], clean_geoms[:10])):
        print(f"  comp {cid}: ({geom.x:.4f}, {geom.y:.4f})")
    print(f"\\nCity locations:")
    for cname, cpt in CITIES.items():
        print(f"  {cname}: ({cpt.x:.4f}, {cpt.y:.4f})")
    raise RuntimeError(f"Too few reference components ({len(ref_idx)}). "
                       f"The scenes covering cities may have failed. "
                       f"Check the STAC processing output above.")
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
    "component_id": clean_cids,
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
is_near_city = np.zeros(len(clean_geoms), dtype=bool)
for city_pt in CITIES.values():
    is_near_city |= (clean_geoms.distance(city_pt) <= exclude_deg).values

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
    twin_ids = set(top["component_id"])
    twin_geo = comp_geo[comp_geo["component_id"].isin(twin_ids)]
    if len(twin_geo):
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
