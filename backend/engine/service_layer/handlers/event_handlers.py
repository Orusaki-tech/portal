from __future__ import annotations

import logging
from uuid import uuid4

from backend.engine.domain.commands import RequestExport
from backend.engine.domain.events import (
    BoundaryCorrected,
    CreditsExhausted,
    ExportCompleted,
    LowConfidenceDetected,
    PolygonValidated,
)
from backend.engine.domain.models import ExportJob
from backend.engine.service_layer.unit_of_work import UnitOfWork

logger = logging.getLogger(__name__)


def handle_request_export(cmd: RequestExport, uow: UnitOfWork) -> dict:
    user = uow.user_repo.get(cmd.user_id)
    if user is None:
        raise ValueError(f"User {cmd.user_id} not found")

    valid_formats = {"geojson", "coco", "yolo", "pascal_voc", "tfrecord", "parquet", "geopackage"}
    if cmd.export_format not in valid_formats:
        raise ValueError(f"Unsupported format: {cmd.export_format}")

    valid_sources = {"dataset", "initiative", "grid"}
    if cmd.source_type not in valid_sources:
        raise ValueError(f"Unsupported source type: {cmd.source_type}")

    job = ExportJob(
        export_id=uuid4(),
        user_id=cmd.user_id,
        export_format=cmd.export_format,
        source_type=cmd.source_type,
        source_id=cmd.source_id,
        status="pending",
        export_params={
            "qa_status": cmd.qa_status,
            "confidence_min": cmd.confidence_min,
            "confidence_max": cmd.confidence_max,
            "annotator_id": str(cmd.annotator_id) if cmd.annotator_id else None,
            "include_original": cmd.include_original,
        },
    )
    uow.export_repo.add(job)

    return {
        "export_id": str(job.export_id),
        "status": "pending",
        "export_format": cmd.export_format,
    }


def handle_classify_confidence(event: PolygonValidated, uow: UnitOfWork) -> None:
    logger.info(f"Polygon {event.polygon_id} validated with confidence {event.confidence}")


def handle_low_confidence_trigger(event: PolygonValidated, uow: UnitOfWork) -> None:
    if event.is_ambiguous:
        logger.info(f"Polygon {event.polygon_id} flagged low confidence ({event.confidence})")


def handle_flag_for_review(event: LowConfidenceDetected, uow: UnitOfWork) -> None:
    logger.info(f"Polygon {event.polygon_id} flagged for review (confidence: {event.confidence})")


def handle_update_geometry(event: BoundaryCorrected, uow: UnitOfWork) -> None:
    logger.info(f"Polygon {event.polygon_id} geometry updated by user {event.user_id}")


def handle_deduct_credits(event: BoundaryCorrected, uow: UnitOfWork) -> None:
    logger.info(f"Credits consumed for correction of polygon {event.polygon_id}")


def handle_credits_exhausted(event: CreditsExhausted, uow: UnitOfWork) -> None:
    logger.warning(f"User {event.user_id} has exhausted credits — validation paused")


def handle_notify_export_complete(event: ExportCompleted, uow: UnitOfWork) -> None:
    logger.info(f"Export {event.export_id} completed for user {event.user_id}: {event.output_url}")
