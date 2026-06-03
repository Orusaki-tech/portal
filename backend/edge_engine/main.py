"""
Entry point for the RealitySync edge validation Cloud Run Job.

Workflow:
  1. Read polygon batch from Cloud SQL or environment input
  2. For each polygon:
     a. Query STAC API for overlapping NAIP imagery
     b. Stream 2-meter pixel buffer around boundary via rio-tiler
     c. Run edge detection pipeline (contrast → K-means → snake)
     d. Compute confidence score
     e. Write vertex-level metrics to Cloud SQL
  3. Trigger dbt run to materialize updated QA statuses
"""

import os
import json
import uuid
from datetime import datetime, timezone

import httpx
import numpy as np
from rio_tiler.io import COGReader
from shapely.geometry import shape, Polygon

from stac_client import find_best_imagery_for_polygon
from edge_detector import (
    enhance_contrast,
    cluster_pixels,
    active_contour_snake,
    measure_deviation,
    compute_spectral_contrast,
)
from confidence_scorer import compute_confidence, is_ambiguous
from models.schemas import EdgeResult, VertexMetric


DB_DSN = os.getenv("DB_DSN", "")
DBT_API_URL = os.getenv("DBT_API_URL", "")
DBT_API_KEY = os.getenv("DBT_API_KEY", "")


def extract_buffer_around_polygon(
    cog_url: str,
    polygon_geometry: dict,
    buffer_meters: float = 2.0,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Stream only the pixel bytes within a buffer strip around the polygon boundary.
    Returns pixel matrix and the affine transform.
    """
    poly = shape(polygon_geometry)
    buffered = poly.buffer(buffer_meters)
    boundary_only = Polygon(buffered.exterior)  # thin strip
    
    with COGReader(cog_url) as cog:
        img = cog.feature(boundary_only.__geointerface__)
    
    return img.data, img.transform


def extract_boundary_vertices(polygon_geometry: dict) -> np.ndarray:
    """Extract the ML-predicted boundary as a numpy array of (x, y) vertices."""
    poly = shape(polygon_geometry)
    coords = list(poly.exterior.coords)
    return np.array(coords)


def process_single_polygon(
    polygon_id: str,
    geometry: dict,
    run_id: str,
    buffer_meters: float = 2.0,
    confidence_threshold: float = 0.7,
) -> EdgeResult:
    # 1. Find overlapping imagery
    imagery = find_best_imagery_for_polygon(geometry)
    if not imagery:
        return EdgeResult(
            polygon_id=polygon_id,
            run_id=run_id,
            is_ambiguous=True,
            confidence_avg=0.0,
            vertices=[],
        )
    
    # 2. Extract pixel buffer
    try:
        pixel_data, transform = extract_buffer_around_polygon(
            imagery["cog_url"], geometry, buffer_meters
        )
    except Exception:
        return EdgeResult(
            polygon_id=polygon_id,
            run_id=run_id,
            is_ambiguous=True,
            confidence_avg=0.0,
            vertices=[],
        )
    
    # Handle single-band vs multi-band
    if pixel_data.ndim == 2:
        pixel_matrix = np.stack([pixel_data] * 3, axis=-1)
    elif pixel_data.shape[0] == 1:
        pixel_matrix = np.stack([pixel_data[0]] * 3, axis=-1)
    else:
        pixel_matrix = np.moveaxis(pixel_data[:3], 0, -1)
    
    # 3. Edge detection pipeline
    enhanced = enhance_contrast(pixel_matrix)
    clustered = cluster_pixels(enhanced, n_clusters=3)
    spectral_contrast = compute_spectral_contrast(pixel_matrix, clustered)
    
    # 4. Active contour snake
    boundary_vertices = extract_boundary_vertices(geometry)
    
    h, w = pixel_matrix.shape[:2]
    center_y, center_x = h // 2, w // 2
    initial_contour = boundary_vertices.copy()
    
    try:
        snake = active_contour_snake(enhanced, initial_contour)
    except Exception:
        snake = initial_contour
    
    # 5. Measure deviation
    mean_deviation, vertex_distances = measure_deviation(initial_contour, snake)
    
    poly_shape = shape(geometry)
    perimeter = poly_shape.length
    
    total_movement = float(np.sum(np.linalg.norm(snake - initial_contour, axis=1)))
    
    # 6. Confidence score
    confidence = compute_confidence(
        spectral_contrast=spectral_contrast,
        total_vertex_movement=total_movement,
        polygon_perimeter=perimeter,
        mean_deviation=mean_deviation,
        buffer_width_meters=buffer_meters,
    )
    
    ambiguous = is_ambiguous(confidence, confidence_threshold)
    
    # 7. Build vertex metrics
    vertices = []
    for i in range(len(vertex_distances)):
        vertices.append(VertexMetric(
            vertex_index=i,
            deviation_meters=float(vertex_distances[i]),
            spectral_contrast=spectral_contrast,
            snake_strain=total_movement / max(perimeter, 1e-6),
            confidence_score=confidence,
        ))
    
    return EdgeResult(
        polygon_id=polygon_id,
        run_id=run_id,
        is_ambiguous=ambiguous,
        confidence_avg=confidence,
        vertices=vertices,
        processed_at=datetime.now(timezone.utc),
    )


def write_results_to_db(results: list[EdgeResult], db_dsn: str):
    """Batch insert edge metrics into Cloud SQL."""
    import psycopg2
    
    conn = psycopg2.connect(db_dsn)
    cur = conn.cursor()
    
    for result in results:
        for vertex in result.vertices:
            cur.execute("""
                INSERT INTO edge_metrics (polygon_id, run_id, vertex_index,
                    deviation_meters, spectral_contrast, snake_strain,
                    confidence_score, is_ambiguous)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                result.polygon_id, result.run_id, vertex.vertex_index,
                vertex.deviation_meters, vertex.spectral_contrast,
                vertex.snake_strain, vertex.confidence_score,
                result.is_ambiguous,
            ))

        qa_status = "low_confidence" if result.is_ambiguous else "validated"
        cur.execute("""
            UPDATE ml_polygons
            SET confidence_avg = %s,
                qa_status = %s
            WHERE id = %s
        """, (result.confidence_avg, qa_status, result.polygon_id))
    
    conn.commit()
    cur.close()
    conn.close()


def trigger_dbt_run():
    """Trigger dbt Cloud job to refresh materialized models."""
    if not DBT_API_URL or not DBT_API_KEY:
        return
    
    with httpx.Client() as client:
        client.post(
            f"{DBT_API_URL}/api/v2/account/12345/run/",
            headers={"Authorization": f"Token {DBT_API_KEY}"},
            json={"cause": "Edge validation completed"},
        )


def main():
    import sys
    
    input_json = os.getenv("INPUT_POLYGONS", "[]")
    run_id = os.getenv("RUN_ID", str(uuid.uuid4()))
    polygons = json.loads(input_json)
    
    results = []
    for poly in polygons:
        result = process_single_polygon(
            polygon_id=poly["id"],
            geometry=poly["geometry"],
            run_id=run_id,
        )
        results.append(result)
    
    write_results_to_db(results, DB_DSN)
    trigger_dbt_run()
    
    print(f"Processed {len(results)} polygons. "
          f"Ambiguous: {sum(1 for r in results if r.is_ambiguous)}")


if __name__ == "__main__":
    main()
