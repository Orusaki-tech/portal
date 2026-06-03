from __future__ import annotations

import logging
from statistics import median
from typing import cast
from uuid import UUID

from shapely import Polygon, wkt

logger = logging.getLogger(__name__)


def merge_annotations(annotations: list[tuple[UUID, str]]) -> str:
    """Merge peer QA annotations into a single WKT geometry.

    * 2 annotations — use Jaccard distance (threshold 1 m²).  Agree → first.
      Disagree → median polygon (centroid / area midpoint).
    * 3+ annotations — majority vote per vertex.
    """
    if not annotations:
        raise ValueError("annotations list must not be empty")

    if len(annotations) == 1:
        return annotations[0][1]

    if len(annotations) == 2:
        return _merge_two(annotations[0][1], annotations[1][1])

    return _merge_many([wkt for _, wkt in annotations])


def _normalize_polygon_coords(poly: Polygon, n_points: int) -> list[tuple[float, float]]:
    """Resample polygon boundary to n_points equally-spaced vertices."""
    boundary = poly.exterior
    distance = boundary.length / n_points
    coords = []
    for i in range(n_points):
        pt = boundary.interpolate(distance * i)
        coords.append((pt.x, pt.y))
    return coords


def _merge_two(wkt_a: str, wkt_b: str) -> str:
    poly_a = wkt.loads(wkt_a)
    poly_b = wkt.loads(wkt_b)

    intersection = poly_a.intersection(poly_b)
    union = poly_a.union(poly_b)
    jaccard_distance = 1.0 - (intersection.area / union.area) if union.area > 0 else 1.0
    threshold = 0.3

    if jaccard_distance < threshold:
        return wkt_a

    n = max(len(list(poly_a.exterior.coords)) - 1, len(list(poly_b.exterior.coords)) - 1, 3)
    coords_a = _normalize_polygon_coords(poly_a, n)
    coords_b = _normalize_polygon_coords(poly_b, n)

    median_coords = [
        (
            (coords_a[i][0] + coords_b[i][0]) / 2.0,
            (coords_a[i][1] + coords_b[i][1]) / 2.0,
        )
        for i in range(n)
    ]
    median_coords.append(median_coords[0])
    return cast(str, Polygon(median_coords).wkt)


def _merge_many(wkts: list[str]) -> str:
    polys = [wkt.loads(w) for w in wkts]
    n = max(len(list(p.exterior.coords)) - 1 for p in polys)
    n = max(n, 3)
    normalized = [_normalize_polygon_coords(p, n) for p in polys]

    merged_coords = []
    for i in range(n):
        xs = [c[i][0] for c in normalized]
        ys = [c[i][1] for c in normalized]
        merged_coords.append((median(xs), median(ys)))

    merged_coords.append(merged_coords[0])
    return cast(str, Polygon(merged_coords).wkt)
