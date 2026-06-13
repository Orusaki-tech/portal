"""
Generate Cloud Optimized GeoTIFFs (COGs) from satellite sources.

Supports three source types:

  - **stac**  — free / public STAC APIs (NAIP, Sentinel-2, Landsat, …)
                → query STAC, return existing COG URL (no reprocessing)
  - **commercial** — paid satellite providers (Planet, Maxar, …)
                → download via provider API → warp → COG → upload to GCS
  - **user_upload** — already a COG in GCS; just return the URL

All results are cached in GCS by source_id + geometry_hash so repeated
requests are instant.
"""

import hashlib
import json
import logging
import os
import subprocess
import tempfile
from dataclasses import dataclass
from typing import Any

from backend.engine.service_layer.preprocessing import build_pipeline as _build_pp

logger = logging.getLogger(__name__)
if not logging.getLogger().handlers:
    logging.basicConfig(level=logging.INFO, format="%(message)s")

from shapely.geometry import mapping, shape

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

PRODUCTION_BUCKET = os.getenv("PRODUCTION_BUCKET", "realitysync-cogs")
COG_KEY_ENCRYPTION_KEY = os.getenv("COG_KEY_ENCRYPTION_KEY", "")


def _db_conn_factory():
    import psycopg2
    return psycopg2.connect(
        host=os.environ.get("DB_HOST", "localhost"),
        port=os.environ.get("DB_PORT", "5432"),
        dbname=os.environ.get("DB_NAME", "realitysync"),
        user=os.environ.get("DB_USER", "realitysync"),
        password=os.environ.get("DB_PASSWORD", "realitysync"),
    )

SOURCE_CONFIG: dict[str, dict[str, Any]] = {
    "naip": {
        "type": "stac",
        "stac_url": "https://planetarycomputer.microsoft.com/api/stac/v1",
        "collection": "naip",
        "asset_key": "image",
        "cloud_cover_field": None,
        "auxiliary_assets": {},
        "pipeline": [],
    },
    "sentinel-2-l2a": {
        "type": "stac",
        "stac_url": "https://planetarycomputer.microsoft.com/api/stac/v1",
        "collection": "sentinel-2-l2a",
        "asset_key": "visual",
        "cloud_cover_field": "eo:cloud_cover",
        "auxiliary_assets": {
            "scl": "SCL",
        },
        "pipeline": [
            {"step": "cloud_mask", "defaults": {"method": "scl", "aux_key": "scl",
             "mask_values": [3, 7, 8, 9, 10]}},
        ],
    },
    "landsat-c2-l2": {
        "type": "stac",
        "stac_url": "https://planetarycomputer.microsoft.com/api/stac/v1",
        "collection": "landsat-c2-l2",
        "asset_key": "rendered_preview",
        "cloud_cover_field": "eo:cloud_cover",
        "auxiliary_assets": {
            "qa_pixel": "qa_pixel",
        },
        "pipeline": [
            {"step": "cloud_mask", "defaults": {"method": "qa_pixel", "aux_key": "qa_pixel",
             "cloud_bits": [3, 4]}},
        ],
    },
    "sentinel-1-rtc": {
        "type": "stac",
        "stac_url": "https://planetarycomputer.microsoft.com/api/stac/v1",
        "collection": "sentinel-1-rtc",
        "asset_key": "visual",
        "cloud_cover_field": None,
        "auxiliary_assets": {},
        "pipeline": [
            {"step": "speckle_filter", "defaults": {"window_size": 7}},
        ],
    },
    "cop-dem-glo-30": {
        "type": "stac",
        "stac_url": "https://planetarycomputer.microsoft.com/api/stac/v1",
        "collection": "cop-dem-glo-30",
        "asset_key": "data",
        "cloud_cover_field": None,
        "auxiliary_assets": {},
        "pipeline": [],
    },
    "cbers-4-mux": {
        "type": "stac",
        "stac_url": "https://data.inpe.br/bdc/stac/v1/",
        "collection": "CBERS4-MUX",
        "asset_key": "image",
        "cloud_cover_field": "eo:cloud_cover",
        "auxiliary_assets": {},
        "pipeline": [],
    },
    "amazonia-1-wfi": {
        "type": "stac",
        "stac_url": "https://data.inpe.br/bdc/stac/v1/",
        "collection": "AMAZONIA1-WFI",
        "asset_key": "image",
        "cloud_cover_field": "eo:cloud_cover",
        "auxiliary_assets": {},
        "pipeline": [],
    },
}

COMMERCIAL_SOURCES: dict[str, Any] = {
    "planet": {"type": "commercial", "provider": "planet"},
    "maxar": {"type": "commercial", "provider": "maxar"},
    "airbus": {"type": "commercial", "provider": "airbus"},
    "blacksky": {"type": "commercial", "provider": "blacksky"},
}

ALL_SOURCES: dict[str, dict[str, Any]] = {**SOURCE_CONFIG, **COMMERCIAL_SOURCES}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _geometry_hash(geojson: dict, source_id: str, buffer_meters: int) -> str:
    raw = json.dumps({"g": geojson, "s": source_id, "b": buffer_meters}, sort_keys=True)
    return hashlib.sha1(raw.encode()).hexdigest()[:20]


def _gcs_cog_path(source_id: str, geo_hash: str) -> str:
    return f"cogs/{source_id}/{geo_hash}.tif"


def _gcs_index_path(source_id: str, geo_hash: str) -> str:
    return f"cogs-index/{source_id}/{geo_hash}.json"


def _public_url(bucket: str, path: str) -> str:
    return f"https://storage.googleapis.com/{bucket}/{path}"


def _gcs_blob_exists(bucket_name: str, blob_name: str) -> bool:
    try:
        from google.cloud import storage
    except ImportError:
        return False
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    return blob.exists()


def _read_gcs_json(bucket_name: str, blob_name: str) -> dict | None:
    try:
        from google.cloud import storage
    except ImportError:
        return None
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    if not blob.exists():
        return None
    raw = blob.download_as_bytes()
    return json.loads(raw)


def _write_gcs_json(bucket_name: str, blob_name: str, data: dict) -> None:
    from google.cloud import storage
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    blob.upload_from_string(json.dumps(data, default=str), content_type="application/json")


def _upload_to_gcs(bucket_name: str, source_path: str, dest_name: str) -> str:
    from google.cloud import storage
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(dest_name)
    blob.upload_from_filename(source_path)
    return _public_url(bucket_name, dest_name)


def _get_source_type(source_id: str) -> str:
    cfg = SOURCE_CONFIG.get(source_id)
    if cfg:
        return cfg["type"]
    cfg = COMMERCIAL_SOURCES.get(source_id)
    if cfg:
        return cfg["type"]
    return "xyz"  # tile-only source (esri-world-imagery, osm, …)


def _check_catalog_overlap(
    conn, source_id: str, polygon
) -> dict | None:
    """Check if a cached COG in the catalog fully contains this polygon."""
    import psycopg2.extras
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT cog_url, cog_size_bytes, scene_id, datetime, resolution, area_km2
            FROM cog_catalog
            WHERE source_id = %s
              AND ST_Contains(bounding_box, ST_GeomFromGeoJSON(%s))
            ORDER BY area_km2 ASC
            LIMIT 1
            """,
            (source_id, json.dumps(mapping(polygon))),
        )
        return cur.fetchone()


def _insert_catalog_entry(
    conn, source_id: str, geo_hash: str, cog_url: str,
    scene_id: str | None, polygon, area_km2: float,
    resolution: float | None, datetime_str: str | None,
    source_type: str = "stac", size_bytes: int | None = None,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO cog_catalog
                (source_id, scene_id, geometry_hash, cog_url, cog_size_bytes,
                 bounding_box, area_km2, resolution, datetime, source_type)
            VALUES (%s, %s, %s, %s, %s,
                    ST_GeomFromGeoJSON(%s), %s, %s, %s::timestamptz, %s)
            ON CONFLICT (source_id, geometry_hash) DO UPDATE
                SET access_count = cog_catalog.access_count + 1
            """,
            (
                source_id, scene_id, geo_hash, cog_url, size_bytes,
                json.dumps(mapping(polygon)), area_km2, resolution,
                datetime_str, source_type,
            ),
        )


# ---------------------------------------------------------------------------
# STAC Scene Finder (Track 1)
# ---------------------------------------------------------------------------


def _sign_stac_urls(item) -> None:
    """Sign asset URLs for providers that require authentication (e.g. Planetary Computer)."""
    # Microsoft Planetary Computer requires SAS token signing
    try:
        from planetary_computer import sign as pc_sign
        signed = pc_sign(item)
        # Replace asset hrefs with signed versions
        for key in list(item.assets.keys()):
            signed_item = signed.assets.get(key)
            if signed_item and signed_item.href:
                item.assets[key].href = signed_item.href
    except ImportError:
        pass  # planetary-computer package not installed; URLs may be unsigned
    except Exception:
        pass  # signing failed; URLs will be as-is (may 403)


def _query_stac(source_id: str, geojson: dict, buffer_meters: int = 0) -> dict[str, Any] | None:
    cfg = SOURCE_CONFIG.get(source_id)
    if not cfg:
        return None

    poly = shape(geojson)
    if buffer_meters > 0:
        poly = poly.buffer(buffer_meters / 111_320.0)
    bbox = list(poly.bounds)

    from pystac_client import Client as StacClient
    catalog = StacClient.open(cfg["stac_url"])
    search = catalog.search(
        collections=[cfg["collection"]],
        bbox=bbox,
        max_items=5,
        sortby=[{"field": "properties.datetime", "direction": "desc"}],
    )
    items = list(search.items())
    if not items:
        return None

    best = items[0]
    _sign_stac_urls(best)
    asset = best.assets.get(cfg["asset_key"])
    if not asset:
        for key in ("image", "cog", "visual", "rendered_preview", "B04", "B05", "data"):
            if key in best.assets:
                asset = best.assets[key]
                break
    if not asset:
        return None

    cog_url = asset.href
    gsd = best.properties.get("gsd") or best.properties.get("eo:gsd", 0)
    area_km2 = compute_geojson_area(geojson, buffer_meters)

    return {
        "cog_url": cog_url,
        "scene_id": best.id,
        "collection": cfg["collection"],
        "datetime": best.properties.get("datetime"),
        "resolution": gsd,
        "bbox": best.bbox,
        "area_km2": area_km2,
        "source_type": "stac",
    }


def compute_geojson_area(geojson: dict, buffer_meters: int = 0) -> float:
    import math
    poly = shape(geojson)
    if buffer_meters > 0:
        poly = poly.buffer(buffer_meters / 111_320.0)
    area = poly.area
    centroid = poly.centroid
    cos_lat = abs(math.cos(math.radians(centroid.y))) if centroid.y is not None else 1.0
    return area * (111_320 ** 2) * cos_lat / 1_000_000  # in km²


# ---------------------------------------------------------------------------
# Commercial Pipeline (Track 2)
# ---------------------------------------------------------------------------


def _download_and_generate_cog(
    source_id: str,
    provider: str,
    geojson: dict,
    buffer_meters: int,
    api_key: str,
) -> dict[str, Any]:
    """Download raw imagery from a commercial provider → warp → COG → upload to GCS."""
    from backend.engine.adapters.commercial_providers import get_provider

    poly = shape(geojson)
    if buffer_meters > 0:
        poly = poly.buffer(buffer_meters / 111_320.0)
    bounds = list(poly.bounds)
    area_km2 = compute_geojson_area(geojson, buffer_meters)

    provider_instance = get_provider(provider)
    if provider_instance is None:
        raise ValueError(f"Provider '{provider}' is not implemented")

    # Search for best scene
    scene = provider_instance.search(poly, api_key)
    if not scene:
        raise ValueError(f"No imagery found from '{provider}' for this area")

    # Estimate cost
    cost = provider_instance.estimate_cost(scene, area_km2)

    # Download
    with tempfile.TemporaryDirectory() as tmpdir:
        raw_path = os.path.join(tmpdir, "raw.tif")
        provider_instance.download(scene["scene_id"], api_key, raw_path)

        # Warp to EPSG:3857
        warped_path = os.path.join(tmpdir, "warped.tif")
        subprocess.run([
            "gdalwarp", raw_path, warped_path,
            "-t_srs", "EPSG:3857",
            "-r", "bilinear",
            "-co", "COMPRESS=DEFLATE",
            "-co", "BIGTIFF=IF_SAFER",
        ], check=True, capture_output=True)

        # Translate to COG
        cog_path = os.path.join(tmpdir, "output_cog.tif")
        subprocess.run([
            "gdal_translate", warped_path, cog_path,
            "-of", "COG",
            "-co", "COMPRESS=DEFLATE",
            "-co", "BLOCKSIZE=512",
            "-co", "OVERVIEWS=IGNORE_EXISTING",
            "-co", "RESAMPLING=LANCZOS",
        ], check=True, capture_output=True)

        # Get file size
        size_bytes = os.path.getsize(cog_path)

        # Upload to GCS
        geo_hash = _geometry_hash(geojson, source_id, buffer_meters)
        dest = _gcs_cog_path(source_id, geo_hash)
        cog_url = _upload_to_gcs(PRODUCTION_BUCKET, cog_path, dest)

    return {
        "cog_url": cog_url,
        "scene_id": scene["scene_id"],
        "datetime": scene.get("datetime"),
        "resolution": scene.get("resolution"),
        "area_km2": area_km2,
        "cost_credits": cost,
        "source_type": "commercial",
        "size_bytes": size_bytes,
    }


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def get_or_generate_cog(
    source_id: str,
    geojson: dict,
    buffer_meters: int = 0,
    force: bool = False,
    api_key: str | None = None,
    user_id: str | None = None,
) -> dict[str, Any]:
    source_type = _get_source_type(source_id)

    geo_hash = _geometry_hash(geojson, source_id, buffer_meters)
    cog_path = _gcs_cog_path(source_id, geo_hash)
    index_path = _gcs_index_path(source_id, geo_hash)

    # 1. Check GCS cache
    if not force:
        if _gcs_blob_exists(PRODUCTION_BUCKET, cog_path):
            meta = _read_gcs_json(PRODUCTION_BUCKET, index_path) or {}
            return {
                "cog_url": _public_url(PRODUCTION_BUCKET, cog_path),
                "cog_size_bytes": meta.get("size_bytes"),
                "cached": True,
                "hash": geo_hash,
                "source_type": source_type,
            }

    if source_type == "stac":
        scene = _query_stac(source_id, geojson, buffer_meters)
        if not scene:
            raise ValueError(f"No imagery found for source '{source_id}' in this area")

        # Cache the scene metadata (no COG file — the STAC asset is already a COG)
        _write_gcs_json(PRODUCTION_BUCKET, index_path, {
            "cog_url": scene["cog_url"],
            "scene_id": scene["scene_id"],
            "collection": scene["collection"],
            "datetime": scene["datetime"],
            "resolution": scene["resolution"],
            "area_km2": scene["area_km2"],
            "source_type": "stac",
        })

        return {
            "cog_url": scene["cog_url"],
            "scene_id": scene["scene_id"],
            "datetime": scene["datetime"],
            "resolution": scene["resolution"],
            "area_km2": scene["area_km2"],
            "cached": False,
            "hash": geo_hash,
            "source_type": "stac",
            "cost_credits": 0,
        }

    elif source_type == "commercial":
        if not api_key:
            # Try user's saved key
            if user_id:
                api_key = _get_saved_provider_key(source_id, user_id)
            if not api_key:
                # Try platform key
                env_var = f"{source_id.upper()}_API_KEY"
                api_key = os.getenv(env_var, "")
            if not api_key:
                raise ValueError(
                    f"No API key for '{source_id}'. Provide your own key or use platform credits."
                )

        result = _download_and_generate_cog(
            source_id=source_id,
            provider=source_id,
            geojson=geojson,
            buffer_meters=buffer_meters,
            api_key=api_key,
        )

        # Write index metadata
        _write_gcs_json(PRODUCTION_BUCKET, index_path, result)

        return result

    else:
        raise ValueError(f"Source '{source_id}' ({source_type}) cannot generate COGs")


def _get_saved_provider_key(source_id: str, user_id: str) -> str | None:
    """Fetch a user's saved API key for a provider from the database."""
    try:
        import psycopg2
        conn = psycopg2.connect(
            host=os.environ.get("DB_HOST", "localhost"),
            port=os.environ.get("DB_PORT", "5432"),
            dbname=os.environ.get("DB_NAME", "realitysync"),
            user=os.environ.get("DB_USER", "realitysync"),
            password=os.environ.get("DB_PASSWORD", "realitysync"),
        )
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT encrypted_key FROM provider_api_keys WHERE user_id = %s AND provider_id = %s",
                    (user_id, source_id),
                )
                row = cur.fetchone()
                if not row:
                    return None
                return _decrypt_key(row[0])
        finally:
            conn.close()
    except Exception:
        return None


# ---------------------------------------------------------------------------
# New Mosaic Pipeline — source-agnostic, two-phase fetch
# ---------------------------------------------------------------------------


@dataclass
class Scene:
    id: str
    url: str
    cloud_cover: float | None = None
    datetime: str | None = None
    footprint: Any = None
    resolution: float | None = None
    aux_urls: dict[str, str] | None = None
    """Auxiliary asset URLs keyed by name (e.g. {"scl": "https://...", "qa_pixel": "..."})."""
    properties: dict | None = None
    """Miscellaneous scene properties (sun_azimuth, sun_elevation, ...)."""


def _mosaic_hash(
    geojson: dict, source_id: str, buffer_meters: int,
    date_from: str | None, date_to: str | None,
    max_cloud_cover: float,
) -> str:
    raw = json.dumps({
        "g": geojson, "s": source_id, "b": buffer_meters,
        "df": date_from, "dt": date_to, "cc": max_cloud_cover,
    }, sort_keys=True)
    return hashlib.sha1(raw.encode()).hexdigest()[:20]


def _query_stac_scenes(
    source_id: str, geojson: dict,
    buffer_meters: int = 0,
    date_from: str | None = None,
    date_to: str | None = None,
    max_cloud_cover: float = 100,
) -> list[Scene]:
    cfg = SOURCE_CONFIG.get(source_id)
    if not cfg:
        raise ValueError(f"Unknown source '{source_id}'")

    from pystac_client import Client as StacClient

    poly = shape(geojson)
    if buffer_meters > 0:
        poly = poly.buffer(buffer_meters / 111_320.0)
    bbox = list(poly.bounds)

    search_params: dict[str, Any] = {
        "collections": [cfg["collection"]],
        "bbox": bbox,
        "max_items": 20,
        "sortby": [{"field": "properties.datetime", "direction": "desc"}],
    }

    query: dict[str, Any] = {}

    cc_field = cfg.get("cloud_cover_field")
    if cc_field and max_cloud_cover < 100:
        query[cc_field] = {"lte": max_cloud_cover}

    if date_from and date_to:
        search_params["datetime"] = f"{date_from}/{date_to}"
    elif date_from:
        search_params["datetime"] = f"{date_from}/.."
    elif date_to:
        search_params["datetime"] = f"../{date_to}"

    if query:
        search_params["query"] = query

    catalog = StacClient.open(cfg["stac_url"])
    try:
        search = catalog.search(**search_params)
        items = list(search.items())
    except Exception as e:
        from backend.engine.service_layer.exceptions import StacUnavailableError
        raise StacUnavailableError(str(e))

    scenes: list[Scene] = []
    for item in items:
        _sign_stac_urls(item)
        asset = item.assets.get(cfg["asset_key"])
        if not asset:
            for key in ("image", "cog", "visual", "rendered_preview", "B04", "B05", "data"):
                if key in item.assets:
                    asset = item.assets[key]
                    break
        if not asset:
            continue

        cc = item.properties.get("eo:cloud_cover") if cc_field else None
        gsd = item.properties.get("gsd") or item.properties.get("eo:gsd", 0)

        # Collect auxiliary asset URLs for preprocessing
        aux_urls: dict[str, str] = {}
        aux_cfg = cfg.get("auxiliary_assets", {})
        for aux_name, aux_key in aux_cfg.items():
            aux_asset = item.assets.get(aux_key)
            if aux_asset and aux_asset.href:
                aux_urls[aux_name] = aux_asset.href

        # Extract key scene properties (sun angles for topographic correction)
        props: dict[str, Any] = {}
        for stac_key in ("sun_azimuth", "sun_elevation", "view:sun_azimuth", "view:sun_elevation"):
            val = item.properties.get(stac_key)
            if val is not None:
                props[stac_key.replace("view:", "")] = val

        scenes.append(Scene(
            id=item.id,
            url=asset.href,
            cloud_cover=float(cc) if cc is not None else None,
            datetime=item.properties.get("datetime"),
            footprint=shape(item.geometry) if item.geometry else None,
            resolution=float(gsd) if gsd else None,
            aux_urls=aux_urls or None,
            properties=props or None,
        ))

    if cc_field:
        scenes.sort(key=lambda s: (s.cloud_cover if s.cloud_cover is not None else 999, s.datetime or ""))

    return scenes


def get_coverage_estimate(
    source_id: str,
    geojson: dict,
    buffer_meters: int = 0,
    date_from: str | None = None,
    date_to: str | None = None,
    max_cloud_cover: float = 100,
) -> dict[str, Any]:
    """Query STAC for scenes matching the polygon and return coverage
    statistics without triggering any COG generation or background job.

    Returns the same scene metadata as ``get_preview_scene`` but also
    includes a ``coverage_pct`` field computed from the union of scene
    footprints.  Raises ``NoScenesFoundError`` when no scenes match the
    given filters.
    """
    source_type = _get_source_type(source_id)
    if source_type != "stac":
        return {
            "preview_available": False,
            "scene_count": 0,
            "coverage_pct": 0,
        }

    scenes = _query_stac_scenes(
        source_id, geojson, buffer_meters,
        date_from, date_to, max_cloud_cover,
    )
    if not scenes:
        from backend.engine.service_layer.exceptions import NoScenesFoundError
        raise NoScenesFoundError()

    poly = shape(geojson)
    if buffer_meters > 0:
        poly = poly.buffer(buffer_meters / 111_320.0)
    target_area = compute_geojson_area(geojson, buffer_meters)

    _, coverage_pct = _check_scene_coverage(scenes, poly)

    dates = [s.datetime for s in scenes if s.datetime]
    cloud_covers = [s.cloud_cover for s in scenes if s.cloud_cover is not None]

    return {
        "preview_available": True,
        "scene_count": len(scenes),
        "scene_ids": [s.id for s in scenes],
        "coverage_pct": round(coverage_pct, 1) if coverage_pct is not None else None,
        "datetime_from": min(dates) if dates else None,
        "datetime_to": max(dates) if dates else None,
        "cloud_cover_avg": round(sum(cloud_covers) / len(cloud_covers), 1) if cloud_covers else None,
        "resolution": getattr(scenes[0], "resolution", None),
        "area_km2": target_area,
        "source_type": source_type,
    }


def _check_scene_coverage(scenes: list[Scene], target_poly) -> tuple[bool, float | None]:
    if not scenes:
        return False, None
    from shapely.ops import unary_union
    footprints = [s.footprint for s in scenes if s.footprint is not None]
    if not footprints or target_poly.area == 0:
        return False, None
    combined = unary_union(footprints)
    overlap = combined.intersection(target_poly).area
    coverage_pct = overlap / target_poly.area * 100
    return combined.contains(target_poly), coverage_pct


def acquire_local_path(scene: Scene, tmpdir: str) -> str:
    stream_path = f"/vsicurl/{scene.url}"
    try:
        result = subprocess.run(
            ["gdalinfo", "-stats", stream_path],
            capture_output=True, timeout=15,
        )
        if result.returncode == 0:
            return stream_path
    except Exception:
        pass

    local_path = os.path.join(tmpdir, f"{scene.id.replace('/', '_')}.tif")
    import httpx
    with httpx.Client(timeout=300.0, follow_redirects=True) as client:
        resp = client.get(scene.url)
        resp.raise_for_status()
        with open(local_path, "wb") as f:
            for chunk in resp.iter_bytes(chunk_size=8 * 1024 * 1024):
                f.write(chunk)
    return local_path


def _build_vrt_mosaic(input_paths: list[str], tmpdir: str) -> str:
    if len(input_paths) == 1:
        return input_paths[0]
    list_path = os.path.join(tmpdir, "scenes.txt")
    with open(list_path, "w") as f:
        for p in input_paths:
            f.write(p + "\n")
    vrt_path = os.path.join(tmpdir, "mosaic.vrt")
    subprocess.run([
        "gdalbuildvrt", "-input_file_list", list_path, vrt_path,
        "-t_srs", "EPSG:4326",
        "-overwrite",
    ], check=True, capture_output=True, timeout=120)
    return vrt_path


def _generate_clipped_cog(
    input_path: str, geojson: dict, buffer_meters: int, tmpdir: str,
) -> tuple[str, int]:
    poly = shape(geojson)
    if buffer_meters > 0:
        poly = poly.buffer(buffer_meters / 111_320.0)

    cutline_path = os.path.join(tmpdir, "cutline.geojson")
    with open(cutline_path, "w") as f:
        json.dump({"type": "Feature", "properties": {}, "geometry": mapping(poly)}, f)

    output_path = os.path.join(tmpdir, "clipped_cog.tif")

    logger.info(
        "Clipping COG: input=%s cutline=%s poly_area_km2=%.2f buffer_m=%d",
        input_path, cutline_path, poly.area * 111_320**2, buffer_meters,
    )

    cmd = [
        "gdalwarp", input_path, output_path,
        "-of", "COG",
        "-t_srs", "EPSG:4326",
        "-cutline", cutline_path,
        "-crop_to_cutline",
        "-dstalpha",
        "-co", "COMPRESS=DEFLATE",
        "-co", "BLOCKSIZE=512",
        "-r", "bilinear",
        "-wm", "1024",
        "-overwrite",
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=300)
    except (subprocess.CalledProcessError, FileNotFoundError):
        logger.warning("Direct COG output failed, falling back to warp+translate")
        warped_path = os.path.join(tmpdir, "warped.tif")
        subprocess.run([
            "gdalwarp", input_path, warped_path,
            "-t_srs", "EPSG:4326",
            "-cutline", cutline_path,
            "-crop_to_cutline",
            "-dstalpha",
            "-co", "COMPRESS=DEFLATE",
            "-r", "bilinear",
        ], check=True, capture_output=True, timeout=300)
        subprocess.run([
            "gdal_translate", warped_path, output_path,
            "-of", "COG",
            "-co", "COMPRESS=DEFLATE",
            "-co", "BLOCKSIZE=512",
            "-co", "RESAMPLING=LANCZOS",
        ], check=True, capture_output=True, timeout=300)

    from osgeo import gdal
    src_ds = gdal.Open(output_path, gdal.GA_ReadOnly)
    if src_ds:
        gt = src_ds.GetGeoTransform()
        width = src_ds.RasterXSize
        height = src_ds.RasterYSize
        bounds = (
            gt[0], gt[3] + height * gt[5],
            gt[0] + width * gt[1], gt[3],
        )
        logger.info(
            "COG clip result: width=%d height=%d bounds=%s size_bytes=%d",
            width, height, bounds, os.path.getsize(output_path),
        )
        src_ds = None

    size_bytes = os.path.getsize(output_path)
    return output_path, size_bytes


# ---------------------------------------------------------------------------
# Background Job Tracking (backed by GCS index file for reliability across
# deploys / cold starts / multiple instances)
# ---------------------------------------------------------------------------


def _job_status_path(job_hash: str) -> str:
    return f"cogs-status/{job_hash}.json"


def get_job_status(job_hash: str) -> dict[str, Any] | None:
    """Return job status from GCS status file, resilient across deploys/instances."""
    try:
        status = _read_gcs_json(PRODUCTION_BUCKET, _job_status_path(job_hash))
        if status:
            return status
    except Exception:
        pass
    return None


def submit_cog_job(
    source_id: str,
    geojson: dict,
    buffer_meters: int = 0,
    date_from: str | None = None,
    date_to: str | None = None,
    max_cloud_cover: float = 100,
    api_key: str | None = None,
    user_id: str | None = None,
    preprocessing_opts: dict[str, Any] | None = None,
) -> str:
    """Submit a Cloud Run Job for COG generation and return the job hash."""
    import sys; print("DIAG: submit_cog_job ENTERED", file=sys.stderr); sys.stderr.flush()
    job_hash = _mosaic_hash(geojson, source_id, buffer_meters, date_from, date_to, max_cloud_cover)

    # Write "processing" status upfront so the status endpoint can immediately
    # find it even if the Cloud Run Job hasn't started yet.
    try:
        _write_gcs_json(PRODUCTION_BUCKET, _job_status_path(job_hash), {
            "status": "processing",
            "source_id": source_id,
            "hash": job_hash,
        })
    except Exception:
        logger.exception("Failed to write initial job status to GCS")

    from backend.engine.service_layer.cloud_run_client import submit_cog_job as _submit_cr_job

    args = dict(
        source_id=source_id,
        geojson=geojson,
        buffer_meters=buffer_meters,
        date_from=date_from,
        date_to=date_to,
        max_cloud_cover=max_cloud_cover,
        api_key=api_key,
        user_id=user_id,
        preprocessing_opts=preprocessing_opts,
    )

    import sys
    try:
        execution_name = _submit_cr_job(args)
        print(f"TRACE: _submit_cr_job OK — execution={execution_name}", file=sys.stderr, flush=True)
    except Exception as e:
        print(f"TRACE: _submit_cr_job FAILED — {e}", file=sys.stderr, flush=True)
        _run_cog_in_process(job_hash, args)

    return job_hash


def _run_cog_in_process(job_hash: str, args: dict) -> str:
    """Fallback when Cloud Run Job submission fails.

    Writes an error status to GCS immediately so the frontend does not spin
    forever.  The in-process path is unreliable on Cloud Run (CPU throttled
    after the HTTP response), so we surface the failure to the user instead.
    """
    logger.error("In-process fallback triggered for job_hash=%s — writing error status", job_hash)
    try:
        _write_gcs_json(PRODUCTION_BUCKET, _job_status_path(job_hash), {
            "status": "error",
            "error": "Cloud Run Job submission failed and in-process fallback is unavailable. Please retry.",
        })
    except Exception:
        logger.exception("Failed to write error status for job_hash=%s", job_hash)
    return job_hash

# Keep old function name for backward compat — it now delegates to the new
# Cloud Run Job path.
generate_clipped_cog_background = submit_cog_job


def _generate_clipped_cog_sync(
    source_id: str,
    geojson: dict,
    buffer_meters: int = 0,
    date_from: str | None = None,
    date_to: str | None = None,
    max_cloud_cover: float = 100,
    api_key: str | None = None,
    user_id: str | None = None,
    preprocessing_opts: dict[str, Any] | None = None,
) -> dict[str, Any]:
    source_type = _get_source_type(source_id)
    job_hash = _mosaic_hash(geojson, source_id, buffer_meters, date_from, date_to, max_cloud_cover)

    poly = shape(geojson)
    if buffer_meters > 0:
        poly = poly.buffer(buffer_meters / 111_320.0)
    target_area = compute_geojson_area(geojson, buffer_meters)

    cog_path_in_gcs = _gcs_cog_path(source_id, job_hash)
    index_path = _gcs_index_path(source_id, job_hash)

    if _gcs_blob_exists(PRODUCTION_BUCKET, cog_path_in_gcs):
        meta = _read_gcs_json(PRODUCTION_BUCKET, index_path) or {}
        return {
            "cog_url": _public_url(PRODUCTION_BUCKET, cog_path_in_gcs),
            "cached": True,
            "hash": job_hash,
            "source_type": source_type,
            "scene_ids": meta.get("scene_ids", []),
            "scene_count": meta.get("scene_count", 0),
            "datetime_from": meta.get("datetime_from"),
            "datetime_to": meta.get("datetime_to"),
            "cloud_cover_avg": meta.get("cloud_cover_avg"),
            "resolution": meta.get("resolution"),
            "area_km2": meta.get("area_km2", target_area),
        }

    with tempfile.TemporaryDirectory() as tmpdir:
        if source_type == "stac":
            logger.info("Querying STAC scenes: source_id=%s", source_id)
            scenes = _query_stac_scenes(
                source_id, geojson, buffer_meters,
                date_from, date_to, max_cloud_cover,
            )
            if not scenes:
                from backend.engine.service_layer.exceptions import NoScenesFoundError
                raise NoScenesFoundError()

            logger.info("Found %d scenes for job_hash=%s", len(scenes), job_hash)

            covered, coverage_pct = _check_scene_coverage(scenes, poly)
            if not covered and coverage_pct is not None and coverage_pct < 80:
                from backend.engine.service_layer.exceptions import CoverageError
                raise CoverageError(
                    f"Scenes cover only {coverage_pct:.0f}% of the target area. "
                    f"Try expanding the date range or raising the cloud cover limit."
                )

            logger.info("Downloading %d scenes to tmpdir", len(scenes))
            inputs = [acquire_local_path(s, tmpdir) for s in scenes]

            # --- Preprocessing pipeline ---
            cfg = SOURCE_CONFIG.get(source_id, {})
            pipeline_cfg_list = cfg.get("pipeline", [])
            has_topo = any(s["step"] == "topographic_correction" for s in pipeline_cfg_list)

            # Query Copernicus DEM if topographic correction is requested
            dem_vrt_path = None
            if has_topo:
                try:
                    dem_scenes = _query_stac_scenes("cop-dem-glo-30", geojson, buffer_meters)
                    if dem_scenes:
                        dem_paths = [acquire_local_path(s, tmpdir) for s in dem_scenes]
                        if len(dem_paths) == 1:
                            dem_vrt_path = dem_paths[0]
                        else:
                            dem_vrt_path = _build_vrt_mosaic(dem_paths, tmpdir)
                except Exception:
                    logger.exception("Failed to query DEM for topographic correction")

            pipeline = _build_pp(source_id, cfg, preprocessing_opts)
            all_aux_paths: list[dict[str, str]] = [{} for _ in scenes]
            if pipeline:
                for i, (scene, input_path) in enumerate(zip(scenes, inputs)):
                    aux_paths: dict[str, str] = {}
                    if scene.aux_urls:
                        for aux_name, aux_url in scene.aux_urls.items():
                            aux_item = Scene(id=f"{scene.id}_{aux_name}", url=aux_url)
                            aux_paths[aux_name] = acquire_local_path(aux_item, tmpdir)

                    # Pass DEM and sun angles for topographic correction
                    if dem_vrt_path:
                        aux_paths["dem"] = dem_vrt_path
                        props_sidecar = os.path.join(tmpdir, f"{scene.id}_props.json")
                        with open(props_sidecar, "w") as f:
                            json.dump({
                                "sun_azimuth": (scene.properties or {}).get("sun_azimuth"),
                                "sun_elevation": (scene.properties or {}).get("sun_elevation"),
                            }, f)
                        aux_paths["scene_props"] = props_sidecar

                    inputs[i] = pipeline.run(input_path, aux_paths, tmpdir)
                    all_aux_paths[i] = aux_paths

                # Run batch steps (radiometric normalization)
                inputs = pipeline.batch_process(inputs, scenes, all_aux_paths, tmpdir)
            # --- End preprocessing ---

            logger.info("Building VRT mosaic from %d inputs", len(inputs))
            if len(inputs) == 1:
                input_path = inputs[0]
            else:
                input_path = _build_vrt_mosaic(inputs, tmpdir)

            logger.info("Clipping COG to polygon: job_hash=%s", job_hash)
            cog_path, size_bytes = _generate_clipped_cog(input_path, geojson, buffer_meters, tmpdir)

            scene_ids = [s.id for s in scenes]
            dates = [s.datetime for s in scenes if s.datetime]
            cloud_covers = [s.cloud_cover for s in scenes if s.cloud_cover is not None]
            resolutions = [s.resolution for s in scenes if s.resolution]

            metadata = {
                "cog_url": _public_url(PRODUCTION_BUCKET, cog_path_in_gcs),
                "scene_ids": scene_ids,
                "scene_count": len(scenes),
                "datetime_from": min(dates) if dates else None,
                "datetime_to": max(dates) if dates else None,
                "cloud_cover_avg": round(sum(cloud_covers) / len(cloud_covers), 1) if cloud_covers else None,
                "resolution": min(resolutions) if resolutions else None,
                "area_km2": target_area,
                "source_type": source_type,
                "size_bytes": size_bytes,
            }

        elif source_type == "commercial":
            from backend.engine.adapters.commercial_providers import get_provider

            if not api_key:
                if user_id:
                    api_key = _get_saved_provider_key(source_id, user_id)
                if not api_key:
                    env_var = f"{source_id.upper()}_API_KEY"
                    api_key = os.getenv(env_var, "")
                if not api_key:
                    raise ValueError(f"No API key for '{source_id}'")

            provider = get_provider(source_id)
            if provider is None:
                raise ValueError(f"Provider '{source_id}' not implemented")

            scene_result = provider.search(poly, api_key)
            if not scene_result:
                raise ValueError(f"No imagery found from '{source_id}'")

            raw_path = os.path.join(tmpdir, "raw.tif")
            provider.download(scene_result[0]["scene_id"], api_key, raw_path)

            cog_path, size_bytes = _generate_clipped_cog(raw_path, geojson, buffer_meters, tmpdir)

            metadata = {
                "cog_url": _public_url(PRODUCTION_BUCKET, cog_path_in_gcs),
                "scene_ids": [scene_result[0]["scene_id"]],
                "scene_count": 1,
                "datetime_from": scene_result[0].get("datetime"),
                "datetime_to": scene_result[0].get("datetime"),
                "cloud_cover_avg": scene_result[0].get("cloud_cover"),
                "resolution": scene_result[0].get("resolution"),
                "area_km2": target_area,
                "source_type": source_type,
                "size_bytes": size_bytes,
            }

        else:
            raise ValueError(f"Source '{source_id}' ({source_type}) cannot generate COGs")

        cog_url = _upload_to_gcs(PRODUCTION_BUCKET, cog_path, cog_path_in_gcs)
        _write_gcs_json(PRODUCTION_BUCKET, index_path, metadata)

        try:
            conn = _db_conn_factory()
            try:
                _insert_catalog_entry(
                    conn, source_id, job_hash, cog_url,
                    metadata.get("scene_ids", [None])[0] if metadata.get("scene_ids") else None,
                    poly, target_area,
                    metadata.get("resolution"),
                    metadata.get("datetime_from"),
                    source_type, size_bytes,
                )
                conn.commit()
            except Exception:
                pass
            finally:
                conn.close()
        except Exception:
            pass

        # Determine what preprocessing steps were applied
        pp_steps = []
        if pipeline_cfg_list:
            pp_steps = [s["step"] for s in pipeline_cfg_list]

        return {
            "cog_url": cog_url,
            "scene_ids": metadata.get("scene_ids", []),
            "scene_count": metadata.get("scene_count", 0),
            "datetime_from": metadata.get("datetime_from"),
            "datetime_to": metadata.get("datetime_to"),
            "cloud_cover_avg": metadata.get("cloud_cover_avg"),
            "resolution": metadata.get("resolution"),
            "area_km2": target_area,
            "cached": False,
            "hash": job_hash,
            "source_type": source_type,
            "preprocessing_applied": pp_steps,
        }


# ---------------------------------------------------------------------------
# Phase 1 — Preview (synchronous, returns best STAC asset URL)
# ---------------------------------------------------------------------------


def get_preview_scene(
    source_id: str,
    geojson: dict,
    buffer_meters: int = 0,
    date_from: str | None = None,
    date_to: str | None = None,
    max_cloud_cover: float = 100,
) -> dict[str, Any]:
    source_type = _get_source_type(source_id)
    if source_type != "stac":
        return {"preview_available": False}

    scenes = _query_stac_scenes(
        source_id, geojson, buffer_meters,
        date_from, date_to, max_cloud_cover,
    )
    if not scenes:
        from backend.engine.service_layer.exceptions import NoScenesFoundError
        raise NoScenesFoundError()

    best = scenes[0]
    target_area = compute_geojson_area(geojson, buffer_meters)
    dates = [s.datetime for s in scenes if s.datetime]
    cloud_covers = [s.cloud_cover for s in scenes if s.cloud_cover is not None]

    return {
        "preview_available": True,
        "preview_url": best.url,
        "scene_count": len(scenes),
        "scene_ids": [s.id for s in scenes],
        "datetime_from": min(dates) if dates else None,
        "datetime_to": max(dates) if dates else None,
        "cloud_cover_avg": round(sum(cloud_covers) / len(cloud_covers), 1) if cloud_covers else None,
        "resolution": best.resolution,
        "area_km2": target_area,
        "source_type": source_type,
    }


def _encrypt_key(plaintext: str) -> str:
    if not COG_KEY_ENCRYPTION_KEY:
        return plaintext  # fallback — store as-is
    from cryptography.fernet import Fernet
    f = Fernet(COG_KEY_ENCRYPTION_KEY.encode())
    return f.encrypt(plaintext.encode()).decode()


def _decrypt_key(ciphertext: str) -> str:
    if not COG_KEY_ENCRYPTION_KEY:
        return ciphertext
    try:
        from cryptography.fernet import Fernet
        f = Fernet(COG_KEY_ENCRYPTION_KEY.encode())
        return f.decrypt(ciphertext.encode()).decode()
    except Exception:
        return ciphertext


# ---------------------------------------------------------------------------
# Credit estimation (no generation — just cost preview)
# ---------------------------------------------------------------------------


def estimate_cost(
    source_id: str,
    geojson: dict,
    buffer_meters: int = 0,
    user_api_key: str | None = None,
) -> dict[str, Any]:
    source_type = _get_source_type(source_id)
    area_km2 = compute_geojson_area(geojson, buffer_meters)

    result = {
        "area_km2": round(area_km2, 4),
        "source_type": source_type,
        "cost_credits": 0,
        "minimum_charge": 0,
        "has_platform_key": False,
        "provider_available": False,
    }

    if source_type == "stac":
        result["cost_credits"] = 0
        result["provider_available"] = True

    elif source_type == "commercial":
        # Check if API key available
        env_key = os.getenv(f"{source_id.upper()}_API_KEY", "")
        has_platform_key = bool(env_key)
        has_user_key = bool(user_api_key)

        if not has_platform_key and not has_user_key:
            result["provider_available"] = False
            return result

        result["provider_available"] = True
        result["has_platform_key"] = has_platform_key

        if user_api_key:
            # BYOK — only service fee
            result["cost_credits"] = max(1, int(area_km2))
            result["minimum_charge"] = 1
        else:
            # Cost per km² depends on provider
            provider_costs = {
                "planet": max(2, int(area_km2 * 2)),
                "maxar": max(5, int(area_km2 * 5)),
                "airbus": max(4, int(area_km2 * 4)),
                "blacksky": max(3, int(area_km2 * 3)),
            }
            cost = provider_costs.get(source_id, max(2, int(area_km2 * 2)))
            result["cost_credits"] = cost
            result["minimum_charge"] = 10

    return result


# ---------------------------------------------------------------------------
# Deduct credits when using platform key for commercial
# ---------------------------------------------------------------------------


def deduct_credits(user_id: str, amount: int) -> None:
    """Deduct credits from a user's balance in the database."""
    import psycopg2
    import uuid
    conn = psycopg2.connect(
        host=os.environ.get("DB_HOST", "localhost"),
        port=os.environ.get("DB_PORT", "5432"),
        dbname=os.environ.get("DB_NAME", "realitysync"),
        user=os.environ.get("DB_USER", "realitysync"),
        password=os.environ.get("DB_PASSWORD", "realitysync"),
    )
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE users SET credits_remaining = credits_remaining - %s WHERE id = %s AND credits_remaining >= %s",
                (amount, user_id, amount),
            )
            if cur.rowcount == 0:
                raise ValueError(f"Insufficient credits. Need {amount}.")
            # Record transaction
            cur.execute(
                """INSERT INTO credit_transactions (user_id, amount, type, description)
                   VALUES (%s, %s, 'cog_generation', %s)""",
                (user_id, -amount, f"COG generation from commercial source"),
            )
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Catalog spatial overlap check (Track 3)
# ---------------------------------------------------------------------------


def find_overlapping_cog(
    source_id: str,
    geojson: dict,
    buffer_meters: int = 0,
) -> dict[str, Any] | None:
    """Check if a cached COG in the catalog already covers this polygon."""
    try:
        import psycopg2
        import psycopg2.extras
    except ImportError:
        return None

    poly = shape(geojson)
    if buffer_meters > 0:
        poly = poly.buffer(buffer_meters / 111_320.0)

    try:
        conn = psycopg2.connect(
            host=os.environ.get("DB_HOST", "localhost"),
            port=os.environ.get("DB_PORT", "5432"),
            dbname=os.environ.get("DB_NAME", "realitysync"),
            user=os.environ.get("DB_USER", "realitysync"),
            password=os.environ.get("DB_PASSWORD", "realitysync"),
        )
        try:
            geo_hash = _geometry_hash(geojson, source_id, buffer_meters)
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                # Exact hash first
                cur.execute(
                    "SELECT cog_url, scene_id, datetime, resolution FROM cog_catalog WHERE source_id = %s AND geometry_hash = %s",
                    (source_id, geo_hash),
                )
                row = cur.fetchone()
                if row:
                    return {"match": dict(row), "match_type": "exact"}

                # Spatial containment
                cur.execute(
                    """SELECT cog_url, scene_id, datetime, resolution, area_km2
                       FROM cog_catalog
                       WHERE source_id = %s
                         AND ST_Contains(bounding_box, ST_GeomFromGeoJSON(%s))
                       ORDER BY area_km2 ASC
                       LIMIT 1""",
                    (source_id, json.dumps(mapping(poly))),
                )
                row = cur.fetchone()
                if row:
                    return {"match": dict(row), "match_type": "containing"}
        finally:
            conn.close()
    except Exception:
        pass

    return None
