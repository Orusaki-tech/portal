"""
Query Microsoft Planetary Computer STAC API for NAIP imagery
matching a given bounding box and date range.
"""

import os
from typing import Any

from pystac_client import Client
from shapely.geometry import box, shape

STAC_API_URL = os.getenv("STAC_API_URL", "https://planetarycomputer.microsoft.com/api/stac/v1")
COLLECTION = os.getenv("STAC_COLLECTION", "naip")


def find_imagery_for_bbox(
    bbox: list[float], datetime_str: str | None = None
) -> list[dict[str, Any]]:
    catalog = Client.open(STAC_API_URL)

    search_params = {
        "collections": [COLLECTION],
        "bbox": bbox,
        "max_items": 5,
    }
    if datetime_str:
        search_params["datetime"] = datetime_str

    results = catalog.search(**search_params)
    items = list(results.items())

    imagery_records = []
    for item in items:
        asset = item.assets.get("image")
        if not asset:
            continue

        imagery_records.append(
            {
                "id": item.id,
                "bbox": item.bbox,
                "geometry": shape(item.geometry).__geointerface__,
                "datetime": item.properties.get("datetime"),
                "cog_url": asset.href,
                "gsd": item.properties.get("gsd"),
            }
        )

    return imagery_records


def find_best_imagery_for_polygon(
    polygon_geometry: dict[str, Any],
    datetime_str: str | None = None,
) -> dict[str, Any] | None:
    poly_shape = shape(polygon_geometry)
    bbox = list(poly_shape.bounds)
    candidates = find_imagery_for_bbox(bbox, datetime_str)

    if not candidates:
        return None

    for candidate in candidates:
        candidate_geom = box(*candidate["bbox"])
        if candidate_geom.intersects(poly_shape):
            return candidate

    return candidates[0]
