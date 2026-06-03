from __future__ import annotations

import logging
import math
from decimal import Decimal
from typing import Any
from uuid import uuid4

from pyproj import Transformer
from shapely import wkt as shapely_wkt

from backend.engine.domain.commands import (
    ApproveGridBlock,
    BulkAssignGridBlocks,
    ClaimGridBlock,
    DisputeGridBlock,
    GenerateGridBlocks,
    LockGridBlock,
    SubmitGridBlock,
)
from backend.engine.domain.events import (
    BoundaryCorrected,
    GridBlockCompleted,
    GridBlockDisputed,
    GridBlockLocked,
    GridBlockSubmitted,
    InitiativeCompleted,
)
from backend.engine.domain.models import GridStatus, InitiativeStatus, TaskGrid
from backend.engine.service_layer.unit_of_work import UnitOfWork

logger = logging.getLogger(__name__)


def handle_lock_grid_block(cmd: LockGridBlock, uow: UnitOfWork) -> dict[str, Any]:
    grid = uow.grid_repo.get(cmd.grid_id)
    if grid is None:
        raise ValueError(f"Grid {cmd.grid_id} not found")

    grid.lock(cmd.user_id)
    grid.raise_event(GridBlockLocked(grid_id=cmd.grid_id, user_id=cmd.user_id))

    return {
        "grid_id": str(cmd.grid_id),
        "status": "in_progress",
        "assigned_user_id": str(cmd.user_id),
    }


def handle_claim_grid_block(cmd: ClaimGridBlock, uow: UnitOfWork) -> dict[str, Any]:
    grids = uow.grid_repo.get_by_initiative(cmd.initiative_id)
    available = [g for g in grids if g.status.value == "pending"]
    if not available:
        raise ValueError(f"No available grids in initiative {cmd.initiative_id}")

    grid = available[0]
    grid.lock(cmd.user_id)
    grid.raise_event(GridBlockLocked(grid_id=grid.id, user_id=cmd.user_id))

    return {
        "grid_id": str(grid.id),
        "status": "in_progress",
        "assigned_user_id": str(cmd.user_id),
    }


def handle_submit_grid_block(cmd: SubmitGridBlock, uow: UnitOfWork) -> dict[str, Any]:
    grid = uow.grid_repo.get(cmd.grid_id)
    if grid is None:
        raise ValueError(f"Grid {cmd.grid_id} not found")

    grid.submit_review()
    grid.raise_event(GridBlockSubmitted(grid_id=cmd.grid_id, user_id=cmd.user_id))

    return {
        "grid_id": str(cmd.grid_id),
        "status": "awaiting_review",
    }


def handle_approve_grid_block(cmd: ApproveGridBlock, uow: UnitOfWork) -> dict[str, Any]:
    grid = uow.grid_repo.get(cmd.grid_id)
    if grid is None:
        raise ValueError(f"Grid {cmd.grid_id} not found")

    reviewer = uow.user_repo.get(cmd.reviewer_id)
    if reviewer is None:
        raise ValueError(f"Reviewer {cmd.reviewer_id} not found")
    if reviewer.role not in ("reviewer", "admin", "manager", "senior_reviewer"):
        raise ValueError(f"User {cmd.reviewer_id} is not authorized to approve grids")

    grid.complete()

    return {
        "grid_id": str(cmd.grid_id),
        "status": "complete",
    }


def handle_dispute_grid_block(cmd: DisputeGridBlock, uow: UnitOfWork) -> dict[str, Any]:
    grid = uow.grid_repo.get(cmd.grid_id)
    if grid is None:
        raise ValueError(f"Grid {cmd.grid_id} not found")

    reviewer = uow.user_repo.get(cmd.reviewer_id)
    if reviewer is None:
        raise ValueError(f"Reviewer {cmd.reviewer_id} not found")
    if reviewer.role not in ("reviewer", "admin", "manager", "senior_reviewer"):
        raise ValueError(f"User {cmd.reviewer_id} is not authorized to dispute grids")

    grid.dispute(cmd.notes)
    grid.raise_event(
        GridBlockDisputed(grid_id=cmd.grid_id, reviewer_id=cmd.reviewer_id, notes=cmd.notes)
    )

    return {
        "grid_id": str(cmd.grid_id),
        "status": "disputed",
    }


def handle_bulk_assign_grid_blocks(cmd: BulkAssignGridBlocks, uow: UnitOfWork) -> dict[str, Any]:
    assigned = 0
    for grid_id in cmd.grid_ids:
        grid = uow.grid_repo.get(grid_id)
        if grid is None:
            continue
        grid.assign_to(cmd.user_id)
        grid.raise_event(GridBlockLocked(grid_id=grid_id, user_id=cmd.user_id))
        assigned += 1

    return {
        "assigned": assigned,
        "total": len(cmd.grid_ids),
    }


def handle_generate_grid_blocks(cmd: GenerateGridBlocks, uow: UnitOfWork) -> dict[str, Any]:
    initiative = uow.initiative_repo.get(cmd.initiative_id)
    if initiative is None:
        raise ValueError(f"Initiative {cmd.initiative_id} not found")

    if initiative.budget_credits is not None and initiative.budget_credits <= Decimal("0"):
        raise ValueError(f"Initiative {cmd.initiative_id} has no budget remaining")

    existing = uow.grid_repo.get_by_initiative(cmd.initiative_id)
    if existing:
        raise ValueError(f"Grids already exist for initiative {cmd.initiative_id}")

    coord_pairs = _parse_polygon_wkt(initiative.region)
    min_lon = min(c[0] for c in coord_pairs)
    max_lon = max(c[0] for c in coord_pairs)
    min_lat = min(c[1] for c in coord_pairs)
    max_lat = max(c[1] for c in coord_pairs)
    grid_size_deg = initiative.grid_size_m / 111_320.0

    transformer = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)

    lat = min_lat
    generated = 0
    while lat < max_lat:
        lon_scale = math.cos(math.radians((lat + min(lat + grid_size_deg, max_lat)) / 2.0))
        lon_step = grid_size_deg / max(lon_scale, 0.01)
        lon = min_lon
        while lon < max_lon:
            cell_lon = min(lon + lon_step, max_lon)
            cell_lat = min(lat + grid_size_deg, max_lat)

            (x, y) = transformer.transform(lon, lat)
            (cell_x, cell_y) = transformer.transform(cell_lon, cell_lat)

            wkt = f"POLYGON(({x} {y}, {cell_x} {y}, {cell_x} {cell_y}, {x} {cell_y}, {x} {y}))"
            grid = TaskGrid(
                id=uuid4(),
                initiative_id=cmd.initiative_id,
                geometry=wkt,
            )
            uow.grid_repo.add(grid)
            generated += 1
            lon += lon_step
        lat += grid_size_deg

    return {
        "initiative_id": str(cmd.initiative_id),
        "grids_generated": generated,
    }


def handle_check_grid_complete(event: BoundaryCorrected, uow: UnitOfWork) -> None:
    logger.info(f"Checking if grid is complete after polygon {event.polygon_id} correction")


def handle_check_initiative_complete(event: GridBlockCompleted, uow: UnitOfWork) -> None:
    logger.info(
        f"Checking if initiative {event.initiative_id} is complete after grid {event.grid_id}"
    )
    initiative = uow.initiative_repo.get(event.initiative_id)
    if initiative is None:
        logger.warning(f"Initiative {event.initiative_id} not found")
        return
    grids = uow.grid_repo.get_by_initiative(event.initiative_id)
    all_complete = all(g.status == GridStatus.COMPLETE for g in grids)
    if all_complete and initiative.status != InitiativeStatus.COMPLETE:
        initiative.complete()
        initiative.raise_event(
            InitiativeCompleted(
                initiative_id=initiative.id,
                owner_id=initiative.owner_id,
            )
        )
        logger.info(f"Initiative {event.initiative_id} marked as completed")


def _parse_polygon_wkt(wkt_str: str) -> list[tuple[float, float]]:
    poly = shapely_wkt.loads(wkt_str)
    return list(poly.exterior.coords)[:-1]
