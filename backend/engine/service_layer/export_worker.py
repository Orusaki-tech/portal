from __future__ import annotations

import base64
import io
import json
import logging
import threading
import time
from typing import Any
from uuid import UUID

from backend.engine.adapters.repository import PostgresExportRepository
from backend.engine.domain.models import ExportJob

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 5

try:
    import pyarrow as pa
    import pyarrow.parquet as pq

    HAS_PARQUET = True
except ImportError:
    HAS_PARQUET = False

try:
    import fiona
    from fiona.crs import from_epsg

    HAS_GEOPACKAGE = True
except ImportError:
    HAS_GEOPACKAGE = False

try:
    import tensorflow as tf

    HAS_TFRECORD = True
except ImportError:
    HAS_TFRECORD = False


def _convert_to_geojson(
    cur: Any, source_type: str, source_id: UUID, export_params: dict[str, Any] | None = None
) -> str:
    if source_type == "grid":
        cur.execute(
            "SELECT p.id, p.polygon_set_id, p.original_geometry, p.corrected_geometry, p.confidence_avg "  # noqa: E501
            "FROM polygons p JOIN task_grids g ON p.task_grid_id = g.id WHERE g.id = %s",
            (source_id,),
        )
    elif source_type == "initiative":
        cur.execute(
            "SELECT p.id, p.polygon_set_id, p.original_geometry, p.corrected_geometry, p.confidence_avg "  # noqa: E501
            "FROM polygons p JOIN task_grids g ON p.task_grid_id = g.id "
            "JOIN initiatives i ON g.initiative_id = i.id WHERE i.id = %s",
            (source_id,),
        )
    else:
        cur.execute(
            "SELECT p.id, p.polygon_set_id, p.original_geometry, p.corrected_geometry, p.confidence_avg "  # noqa: E501
            "FROM polygons p WHERE p.polygon_set_id = %s",
            (source_id,),
        )

    features: list[dict[str, Any]] = []
    for row in cur.fetchall():
        wkt = row[3] or row[2]
        coords = _wkt_to_geojson_coords(wkt)
        feat: dict[str, Any] = {
            "type": "Feature",
            "id": str(row[0]),
            "geometry": {"type": "Polygon", "coordinates": [coords]},
            "properties": {
                "polygon_set_id": str(row[1]) if row[1] else None,
                "confidence_avg": float(row[4]) if row[4] else None,
            },
        }
        if export_params:
            if not export_params.get("include_original", True) and row[3] is None:
                continue
            conf = feat["properties"].get("confidence_avg")
            if export_params.get("confidence_min") is not None and (
                conf is None or conf < export_params["confidence_min"]
            ):
                continue
            if export_params.get("confidence_max") is not None and (
                conf is not None and conf > export_params["confidence_max"]
            ):
                continue
        features.append(feat)

    return json.dumps({"type": "FeatureCollection", "features": features}, indent=2)


def _wkt_to_geojson_coords(wkt_str: str) -> list[list[float]]:
    from shapely import wkt as shapely_wkt

    geom = shapely_wkt.loads(wkt_str)
    return list(geom.exterior.coords)


def _convert_to_coco(
    cur: Any, source_type: str, source_id: UUID, export_params: dict[str, Any] | None = None
) -> str:
    geojson = json.loads(_convert_to_geojson(cur, source_type, source_id, export_params))
    images: list[dict[str, Any]] = []
    annotations: list[dict[str, Any]] = []

    all_x: list[float] = []
    all_y: list[float] = []

    for feat in geojson["features"]:
        for ring in feat["geometry"]["coordinates"][0]:
            all_x.append(ring[0])
            all_y.append(ring[1])

    img_w = max(all_x) - min(all_x) if all_x else 1000
    img_h = max(all_y) - min(all_y) if all_y else 1000

    for i, feat in enumerate(geojson["features"]):
        ann_id = i + 1
        coords = feat["geometry"]["coordinates"]
        flat = [[round(c, 6) for c in ring] for ring in coords[0]]
        xs = [c[0] for c in coords[0]]
        ys = [c[1] for c in coords[0]]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        bbox_w = max_x - min_x
        bbox_h = max_y - min_y
        annotations.append(
            {
                "id": ann_id,
                "image_id": 1,
                "category_id": 1,
                "segmentation": [flat],
                "area": round(bbox_w * bbox_h, 4),
                "bbox": [round(min_x, 6), round(min_y, 6), round(bbox_w, 6), round(bbox_h, 6)],
                "iscrowd": 0,
            }
        )
    images.append(
        {"id": 1, "file_name": "source", "width": round(img_w, 6), "height": round(img_h, 6)}
    )
    return json.dumps(
        {
            "images": images,
            "annotations": annotations,
            "categories": [{"id": 1, "name": "polygon", "supercategory": "boundary"}],
        },
        indent=2,
    )


def _convert_to_yolo(
    cur: Any, source_type: str, source_id: UUID, export_params: dict[str, Any] | None = None
) -> str:
    geojson = json.loads(_convert_to_geojson(cur, source_type, source_id, export_params))
    all_coords = []
    for feat in geojson["features"]:
        all_coords.extend(feat["geometry"]["coordinates"][0])
    xs = [c[0] for c in all_coords]
    ys = [c[1] for c in all_coords]
    x_min, x_max = min(xs), max(xs)
    y_min, y_max = min(ys), max(ys)
    x_range = x_max - x_min or 1.0
    y_range = y_max - y_min or 1.0

    lines: list[str] = []
    for feat in geojson["features"]:
        coords = feat["geometry"]["coordinates"][0]
        cx = sum(c[0] for c in coords) / len(coords)
        cy = sum(c[1] for c in coords) / len(coords)
        xs_poly = [c[0] for c in coords]
        ys_poly = [c[1] for c in coords]
        w = max(xs_poly) - min(xs_poly)
        h = max(ys_poly) - min(ys_poly)
        nx = (cx - x_min) / x_range
        ny = (cy - y_min) / y_range
        nw = w / x_range
        nh = h / y_range
        lines.append(f"0 {nx:.6f} {ny:.6f} {nw:.6f} {nh:.6f}")
    return "\n".join(lines)


def _convert_to_pascal_voc(
    cur: Any, source_type: str, source_id: UUID, export_params: dict[str, Any] | None = None
) -> str:
    geojson = json.loads(_convert_to_geojson(cur, source_type, source_id, export_params))
    parts: list[str] = ["<annotation>"]
    for feat in geojson["features"]:
        parts.append("  <object><name>polygon</name><polygon>")
        for pt in feat["geometry"]["coordinates"][0]:
            parts.append(f"    <pt><x>{pt[0]}</x><y>{pt[1]}</y></pt>")
        parts.append("  </polygon></object>")
    parts.append("</annotation>")
    return "\n".join(parts)


def _convert_to_parquet(
    cur: Any, source_type: str, source_id: UUID, export_params: dict[str, Any] | None = None
) -> str:
    geojson = json.loads(_convert_to_geojson(cur, source_type, source_id, export_params))
    rows: list[dict[str, Any]] = []
    for feat in geojson["features"]:
        rows.append(
            {
                "polygon_id": feat.get("id", ""),
                "polygon_set_id": feat.get("properties", {}).get("polygon_set_id"),
                "confidence_avg": feat.get("properties", {}).get("confidence_avg"),
                "wkt": f"POLYGON(({','.join(f'{c[0]} {c[1]}' for c in feat['geometry']['coordinates'][0])}))",  # noqa: E501
            }
        )
    if HAS_PARQUET:
        table = pa.Table.from_pylist(rows)
        buf = pa.BufferOutputStream()
        pq.write_table(table, buf)
        return base64.b64encode(buf.getvalue().to_pybytes()).decode()
    return json.dumps(rows, indent=2)


def _convert_to_geopackage(
    cur: Any, source_type: str, source_id: UUID, export_params: dict[str, Any] | None = None
) -> str:
    geojson = json.loads(_convert_to_geojson(cur, source_type, source_id, export_params))
    features = geojson.get("features", [])
    if HAS_GEOPACKAGE:
        buf = io.BytesIO()
        schema = {
            "geometry": "Polygon",
            "properties": [
                ("polygon_id", "str"),
                ("polygon_set_id", "str"),
                ("confidence_avg", "float"),
            ],
        }
        with fiona.open(buf, "w", driver="GPKG", schema=schema, crs=from_epsg(4326)) as dst:
            for feat in features:
                dst.write(
                    {
                        "geometry": feat["geometry"],
                        "properties": {
                            "polygon_id": feat.get("id", ""),
                            "polygon_set_id": feat.get("properties", {}).get("polygon_set_id", ""),
                            "confidence_avg": feat.get("properties", {}).get("confidence_avg", 0.0),
                        },
                    }
                )
        return base64.b64encode(buf.getvalue()).decode()
    return json.dumps(features, indent=2)


def _convert_to_tfrecord(
    cur: Any, source_type: str, source_id: UUID, export_params: dict[str, Any] | None = None
) -> str:
    geojson = json.loads(_convert_to_geojson(cur, source_type, source_id, export_params))
    if not HAS_TFRECORD:
        return json.dumps({"error": "tensorflow not installed"}, indent=2)
    buf = io.BytesIO()
    with tf.io.TFRecordWriter(buf) as writer:
        for feat in geojson.get("features", []):
            coords = feat["geometry"]["coordinates"][0]
            feature = tf.train.Features(
                feature={
                    "polygon_id": tf.train.Feature(
                        bytes_list=tf.train.BytesList(value=[str(feat.get("id", "")).encode()])
                    ),
                    "coordinates": tf.train.Feature(
                        float_list=tf.train.FloatList(value=[c for pt in coords for c in pt])
                    ),
                    "confidence_avg": tf.train.Feature(
                        float_list=tf.train.FloatList(
                            value=[feat.get("properties", {}).get("confidence_avg", 0.0)]
                        )
                    ),
                }
            )
            writer.write(tf.train.Example(features=feature).SerializeToString())
    return base64.b64encode(buf.getvalue()).decode()


FORMAT_CONVERTERS = {
    "geojson": ("geojson", _convert_to_geojson),
    "coco": ("json", _convert_to_coco),
    "yolo": ("txt", _convert_to_yolo),
    "pascal_voc": ("xml", _convert_to_pascal_voc),
    "parquet": ("parquet", _convert_to_parquet),
    "geopackage": ("gpkg", _convert_to_geopackage),
    "tfrecord": ("tfrecord", _convert_to_tfrecord),
}


class ExportWorker:
    """Background worker that polls for pending export jobs and processes them.

    In production this would invoke format-specific converters (GeoJSON, COCO, etc.)
    and upload the result to cloud storage.  For MVP it creates a placeholder URL.
    """

    def __init__(self, connection_factory: Any) -> None:
        self._factory = connection_factory
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            logger.warning("ExportWorker already running")
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop,
            name="export-worker",
            daemon=True,
        )
        self._thread.start()
        logger.info("ExportWorker started (poll interval=%ss)", POLL_INTERVAL_SECONDS)

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=10)
        logger.info("ExportWorker stopped")

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._process_pending_jobs()
            except Exception:
                logger.exception("ExportWorker error — will retry")
            time.sleep(POLL_INTERVAL_SECONDS)

    def _process_pending_jobs(self) -> None:
        conn = self._factory()
        try:
            repo = PostgresExportRepository(conn)
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT export_id, user_id, export_format, source_type, source_id, export_params "  # noqa: E501
                    "FROM export_jobs WHERE status = 'pending' ORDER BY created_at ASC"
                )
                for row in cur.fetchall():
                    job = ExportJob(
                        export_id=row[0],
                        user_id=row[1],
                        export_format=row[2],
                        source_type=row[3],
                        source_id=row[4],
                        status="pending",
                        export_params=row[5],
                    )
                    self._complete_job(repo, cur, job)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _complete_job(
        self,
        repo: PostgresExportRepository,
        cur: Any,
        job: ExportJob,
    ) -> None:
        ext, converter = FORMAT_CONVERTERS.get(job.export_format, ("bin", None))

        if converter:
            try:
                content = converter(cur, job.source_type, job.source_id, job.export_params or {})
                content_bytes = content.encode("utf-8")
                output_url = (
                    f"https://storage.realitysync.app/exports/{job.export_id}/{job.export_id}.{ext}"
                )
                logger.info(
                    "Export %s converted: %s (%d bytes)",
                    job.export_id,
                    job.export_format,
                    len(content_bytes),
                )
            except Exception:
                logger.exception("Export %s conversion failed", job.export_id)
                cur.execute(
                    "UPDATE export_jobs SET status = 'failed', completed_at = now() WHERE export_id = %s",  # noqa: E501
                    (job.export_id,),
                )
                return
        else:
            output_url = (
                f"https://storage.realitysync.app/exports/{job.export_id}/{job.export_id}.{ext}"
            )

        cur.execute(
            """
            UPDATE export_jobs
            SET status = 'completed', output_url = %s, completed_at = now()
            WHERE export_id = %s
            """,
            (output_url, job.export_id),
        )

        logger.info(
            "Export %s completed: %s -> %s",
            job.export_id,
            job.export_format,
            output_url,
        )
