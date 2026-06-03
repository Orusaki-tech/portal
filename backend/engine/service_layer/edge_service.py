from __future__ import annotations

import logging
import math

from shapely import wkt
from shapely.geometry import Polygon, shape

logger = logging.getLogger(__name__)

_PIPELINE_AVAILABLE = False
try:
    import numpy as np

    from backend.edge_engine.confidence_scorer import compute_confidence, is_ambiguous

    _PIPELINE_AVAILABLE = True
except ImportError:
    logger.info("Heavy edge deps not available — using heuristic validation")


def _wkt_to_coords(geometry: str) -> list[tuple[float, float]]:
    poly = wkt.loads(geometry)
    return list(poly.exterior.coords)


def _heuristic_confidence(geometry: str) -> tuple[float, bool]:
    coords = _wkt_to_coords(geometry)
    n = len(coords)
    if n < 4:
        return (0.0, True)

    area = 0.0
    for i in range(n):
        x1, y1 = coords[i]
        x2, y2 = coords[(i + 1) % n]
        area += x1 * y2 - x2 * y1
    area = abs(area) / 2.0

    perim = 0.0
    for i in range(n):
        x1, y1 = coords[i]
        x2, y2 = coords[(i + 1) % n]
        perim += math.hypot(x2 - x1, y2 - y1)

    if area < 1e-10 or perim < 1e-10:
        return (0.0, True)

    compactness = (4.0 * math.pi * area) / (perim * perim)
    compactness_score = min(compactness, 1.0)

    vertex_penalty = 0.0
    if n < 5:
        vertex_penalty = 0.2
    elif n > 20:
        vertex_penalty = 0.1 * (float(n) / 10.0)

    confidence = max(0.0, min(1.0, compactness_score * 0.7 + 0.3 - vertex_penalty))
    ambiguous = confidence < 0.70
    return (round(confidence, 4), ambiguous)


def validate_polygon(
    geometry: str,
    imagery_source: str = "naip",
    imagery_priority: list[str] | None = None,
) -> dict:
    sources = imagery_priority or [imagery_source]
    last_error: str | None = None

    for src in sources:
        if _PIPELINE_AVAILABLE:
            try:
                return _run_pipeline(geometry, src)
            except Exception as e:
                last_error = str(e)
                logger.warning("Edge pipeline failed for source %s — trying next", src)
        else:
            break

    if last_error:
        logger.warning("All imagery sources failed (%s) — falling back to heuristic", last_error)

    confidence, ambiguous = _heuristic_confidence(geometry)
    return {
        "confidence_avg": confidence,
        "is_ambiguous": ambiguous,
        "source": "heuristic",
    }


def _run_pipeline(geometry: str, imagery_source: str) -> dict:
    poly_shape = shape({"type": "Polygon", "coordinates": [_wkt_to_coords(geometry)]})

    from backend.edge_engine.stac_client import find_best_imagery_for_polygon

    imagery = find_best_imagery_for_polygon(poly_shape.__geointerface__)
    if not imagery:
        confidence, ambiguous = _heuristic_confidence(geometry)
        return {"confidence_avg": confidence, "is_ambiguous": ambiguous, "source": "heuristic"}

    from backend.edge_engine.edge_detector import (
        active_contour_snake,
        cluster_pixels,
        compute_spectral_contrast,
        enhance_contrast,
        measure_deviation,
    )

    try:
        pixel_data, _ = _extract_buffer(poly_shape.__geointerface__, imagery["cog_url"])
    except Exception:
        confidence, ambiguous = _heuristic_confidence(geometry)
        return {"confidence_avg": confidence, "is_ambiguous": ambiguous, "source": "heuristic"}

    if pixel_data.ndim == 2:
        pixel_matrix = np.stack([pixel_data] * 3, axis=-1)
    elif pixel_data.shape[0] == 1:
        pixel_matrix = np.stack([pixel_data[0]] * 3, axis=-1)
    else:
        pixel_matrix = np.moveaxis(pixel_data[:3], 0, -1)

    enhanced = enhance_contrast(pixel_matrix)
    clustered = cluster_pixels(enhanced, n_clusters=3)
    spectral_contrast = compute_spectral_contrast(pixel_matrix, clustered)

    boundary_vertices = _extract_vertices(poly_shape.__geointerface__)
    try:
        snake = active_contour_snake(enhanced, boundary_vertices)
    except Exception:
        snake = boundary_vertices

    mean_deviation, _ = measure_deviation(boundary_vertices, snake)
    total_movement = float(np.sum(np.linalg.norm(snake - boundary_vertices, axis=1)))
    perimeter = poly_shape.length

    confidence = compute_confidence(
        spectral_contrast=spectral_contrast,
        total_vertex_movement=total_movement,
        polygon_perimeter=perimeter,
        mean_deviation=mean_deviation,
        buffer_width_meters=2.0,
    )

    ambiguous = is_ambiguous(confidence)
    return {"confidence_avg": confidence, "is_ambiguous": ambiguous, "source": "pipeline"}


def _extract_buffer(
    polygon_geometry: dict, cog_url: str, buffer_meters: float = 2.0
) -> tuple[np.ndarray, object]:
    poly = shape(polygon_geometry)
    buffered = poly.buffer(buffer_meters)
    boundary_only = Polygon(buffered.exterior)

    from rio_tiler.io import Reader as COGReader

    with COGReader(cog_url) as cog:
        img = cog.feature(boundary_only.__geointerface__)

    return img.data, img.transform


def _extract_vertices(polygon_geometry: dict) -> np.ndarray:
    poly = shape(polygon_geometry)
    coords = list(poly.exterior.coords)
    return np.array(coords)
