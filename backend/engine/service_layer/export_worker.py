from __future__ import annotations

import logging
import threading
import time
from uuid import UUID, uuid4

from backend.engine.adapters.repository import PostgresExportRepository
from backend.engine.domain.events import ExportCompleted
from backend.engine.domain.models import ExportJob

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 5


class ExportWorker:
    """Background worker that polls for pending export jobs and processes them.

    In production this would invoke format-specific converters (GeoJSON, COCO, etc.)
    and upload the result to cloud storage.  For MVP it creates a placeholder URL.
    """

    def __init__(self, connection_factory: object) -> None:
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
                    "SELECT * FROM export_jobs WHERE status = 'pending' ORDER BY created_at ASC"
                )
                for row in cur.fetchall():
                    job = ExportJob(
                        export_id=row[0],
                        user_id=row[1],
                        export_format=row[2],
                        source_type=row[3],
                        source_id=row[4],
                        status="pending",
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
        cur: object,
        job: ExportJob,
    ) -> None:
        format_map = {
            "geojson": "geojson",
            "coco": "json",
            "yolo": "txt",
            "pascal_voc": "xml",
            "tfrecord": "tfrecord",
        }
        ext = format_map.get(job.export_format, "bin")
        output_url = (
            f"https://storage.realitysync.app/exports/"
            f"{job.export_id}/{job.export_id}.{ext}"
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
            job.export_id, job.export_format, output_url,
        )
