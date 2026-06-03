from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any
from uuid import uuid4

from backend.engine.domain.commands import CorrectBoundary, UploadPolygonSet, ValidatePolygon
from backend.engine.domain.events import (
    BoundaryCorrected,
    ConsensusReached,
    PolygonValidated,
)
from backend.engine.domain.models import (
    Correction,
    CreditTransaction,
    Polygon,
    PolygonSet,
    QaStatus,
    TaskGrid,
)
from backend.engine.service_layer.edge_service import validate_polygon
from backend.engine.service_layer.unit_of_work import UnitOfWork

logger = logging.getLogger(__name__)


def handle_validate_polygon(cmd: ValidatePolygon, uow: UnitOfWork) -> dict[str, Any]:
    grid = uow.grid_repo.get(cmd.grid_id)
    if grid is None:
        raise ValueError(f"Grid {cmd.grid_id} not found")

    polygon = next((p for p in grid.polygons if p.id == cmd.polygon_id), None)
    if polygon is None:
        raise ValueError(f"Polygon {cmd.polygon_id} not found in grid")

    if cmd.user_id:
        user = uow.user_repo.get(cmd.user_id)
        if user is None:
            raise ValueError(f"User {cmd.user_id} not found")
        user.deduct_credits(Decimal("1"))
        uow.credit_txn_repo.add(
            CreditTransaction(
                id=uuid4(),
                user_id=cmd.user_id,
                amount=Decimal("-1"),
                transaction_type="validation",
                reference_id=cmd.polygon_id,
                description=f"Validation of polygon {cmd.polygon_id} in grid {cmd.grid_id}",
            )
        )

    result = validate_polygon(
        geometry=polygon.original_geometry,
        imagery_source=cmd.imagery_source,
        imagery_priority=None,
    )
    polygon.confidence_avg = result["confidence_avg"]

    if result["is_ambiguous"]:
        polygon.qa_status = QaStatus.LOW_CONFIDENCE
    else:
        polygon.qa_status = QaStatus.VALIDATED

    grid.raise_event(
        PolygonValidated(
            polygon_id=polygon.id,
            confidence=result["confidence_avg"],
            is_ambiguous=result["is_ambiguous"],
        )
    )

    return {
        "polygon_id": str(cmd.polygon_id),
        "grid_id": str(cmd.grid_id),
        "status": polygon.qa_status.value,
        "confidence": polygon.confidence_avg,
    }


def handle_upload_polygon_set(cmd: UploadPolygonSet, uow: UnitOfWork) -> dict[str, Any]:
    user = uow.user_repo.get(cmd.user_id)
    if user is None:
        raise ValueError(f"User {cmd.user_id} not found")

    from backend.engine.domain.models import Initiative as InitiativeModel

    initiative = InitiativeModel(
        id=uuid4(),
        owner_id=cmd.user_id,
        name=f"Set: {cmd.name}",
        region="POLYGON((-122.5 37.5, -122.0 37.5, -122.0 38.0, -122.5 38.0, -122.5 37.5))",
    )
    uow.initiative_repo.add(initiative)

    grid_id = uuid4()
    grid = TaskGrid(
        id=grid_id,
        initiative_id=initiative.id,
        geometry="POLYGON((-122.5 37.5, -122.0 37.5, -122.0 38.0, -122.5 38.0, -122.5 37.5))",
    )

    polygon_set_id = uuid4()
    polygon_set = PolygonSet(
        id=polygon_set_id,
        user_id=cmd.user_id,
        name=cmd.name,
        model_version=cmd.model_version,
    )
    uow.polygon_set_repo.add(polygon_set)

    for i, geom in enumerate(cmd.geometries):
        polygon = Polygon(
            id=uuid4(),
            task_grid_id=grid_id,
            polygon_set_id=polygon_set_id,
            original_geometry=geom,
        )
        grid.polygons.append(polygon)

    uow.grid_repo.add(grid)

    return {
        "set_id": str(polygon_set_id),
        "polygon_count": len(cmd.geometries),
    }


def handle_correct_boundary(cmd: CorrectBoundary, uow: UnitOfWork) -> dict[str, Any]:
    grid = uow.grid_repo.get(cmd.grid_id)
    if grid is not None:
        polygon = next((p for p in grid.polygons if p.id == cmd.polygon_id), None)
    else:
        polygon = uow.polygon_repo.get(cmd.polygon_id) if hasattr(uow, "polygon_repo") else None

    if polygon is None:
        raise ValueError(f"Polygon {cmd.polygon_id} not found")

    original = polygon.original_geometry
    polygon.correct(cmd.new_geometry)

    correction = Correction(
        id=uuid4(),
        polygon_id=cmd.polygon_id,
        user_id=cmd.user_id,
        original_geometry=original,
        corrected_geometry=cmd.new_geometry,
        action="correct",
    )
    uow.correction_repo.add(correction)

    if grid is not None:
        grid.raise_event(
            BoundaryCorrected(
                polygon_id=cmd.polygon_id,
                user_id=cmd.user_id,
                new_geometry=cmd.new_geometry,
            )
        )

    corrections = uow.correction_repo.get_by_polygon(cmd.polygon_id)
    if len(corrections) >= 2:
        from backend.engine.service_layer.consensus import merge_annotations

        annotations = [(c.user_id, c.corrected_geometry) for c in corrections]
        merged = merge_annotations(annotations)
        polygon.correct(merged)
        polygon.qa_status = QaStatus.VALIDATED
        polygon.confidence_avg = 0.95
        if grid is not None:
            grid.raise_event(
                ConsensusReached(
                    polygon_id=cmd.polygon_id,
                    merged_geometry=merged,
                    annotation_count=len(corrections),
                )
            )

    return {
        "polygon_id": str(cmd.polygon_id),
        "grid_id": str(cmd.grid_id),
        "status": "corrected",
    }
