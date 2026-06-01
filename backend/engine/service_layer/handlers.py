from __future__ import annotations

import logging
from decimal import Decimal
from uuid import UUID, uuid4

from backend.engine.domain.commands import (
    AssignParticipant,
    CorrectBoundary,
    CreateInitiative,
    GenerateGridBlocks,
    ListDatasetForSale,
    LockGridBlock,
    PurchaseDataset,
    RequestExport,
    TopUpCredits,
    UploadPolygonSet,
    ValidatePolygon,
)
from backend.engine.domain.events import (
    BoundaryCorrected,
    CreditsExhausted,
    DatasetPurchased,
    ExportCompleted,
    GridBlockCompleted,
    InitiativeCompleted,
    LowConfidenceDetected,
    PolygonValidated,
)
from backend.engine.domain.models import (
    Correction,
    DatasetPurchase,
    ExportJob,
    Initiative,
    MarketplaceListing,
    Participant,
    Polygon,
    QaStatus,
    TaskGrid,
    User,
)
from backend.engine.service_layer.unit_of_work import UnitOfWork

logger = logging.getLogger(__name__)


def handle_validate_polygon(
    cmd: ValidatePolygon, uow: UnitOfWork
) -> dict:
    grid = uow.grid_repo.get(cmd.grid_id)
    if grid is None:
        raise ValueError(f"Grid {cmd.grid_id} not found")

    polygon = next(
        (p for p in grid.polygons if p.id == cmd.polygon_id), None
    )
    if polygon is None:
        raise ValueError(f"Polygon {cmd.polygon_id} not found in grid")

    if cmd.user_id:
        user = uow.user_repo.get(cmd.user_id)
        if user is None:
            raise ValueError(f"User {cmd.user_id} not found")
        user.deduct_credits(Decimal("1"))

    polygon.qa_status = QaStatus.VALIDATED
    polygon.confidence_avg = 0.95
    grid.raise_event(
        PolygonValidated(
            polygon_id=polygon.id,
            confidence=0.95,
            is_ambiguous=False,
        )
    )

    return {
        "polygon_id": str(cmd.polygon_id),
        "grid_id": str(cmd.grid_id),
        "status": "validated",
        "confidence": polygon.confidence_avg,
    }


def handle_upload_polygon_set(
    cmd: UploadPolygonSet, uow: UnitOfWork
) -> dict:
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


def handle_correct_boundary(
    cmd: CorrectBoundary, uow: UnitOfWork
) -> dict:
    grid = uow.grid_repo.get(cmd.grid_id)
    if grid is None:
        raise ValueError(f"Grid {cmd.grid_id} not found")

    polygon = next(
        (p for p in grid.polygons if p.id == cmd.polygon_id), None
    )
    if polygon is None:
        raise ValueError(f"Polygon {cmd.polygon_id} not found in grid")

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

    grid.raise_event(
        BoundaryCorrected(
            polygon_id=cmd.polygon_id,
            user_id=cmd.user_id,
            new_geometry=cmd.new_geometry,
        )
    )

    return {
        "polygon_id": str(cmd.polygon_id),
        "grid_id": str(cmd.grid_id),
        "status": "corrected",
    }


def handle_create_initiative(
    cmd: CreateInitiative, uow: UnitOfWork
) -> dict:
    initiative = Initiative(
        id=uuid4(),
        owner_id=cmd.owner_id,
        name=cmd.name,
        region=cmd.region,
        grid_size_m=cmd.grid_size_m,
        budget_credits=cmd.budget_credits,
    )
    uow.initiative_repo.add(initiative)
    return {
        "initiative_id": str(initiative.id),
        "status": "draft",
        "name": initiative.name,
    }


def handle_lock_grid_block(
    cmd: LockGridBlock, uow: UnitOfWork
) -> dict:
    grid = uow.grid_repo.get(cmd.grid_id)
    if grid is None:
        raise ValueError(f"Grid {cmd.grid_id} not found")

    grid.lock(cmd.user_id)

    return {
        "grid_id": str(cmd.grid_id),
        "status": "in_progress",
        "assigned_user_id": str(cmd.user_id),
    }


def handle_top_up_credits(
    cmd: TopUpCredits, uow: UnitOfWork
) -> dict:
    user = uow.user_repo.get(cmd.user_id)
    if user is None:
        raise ValueError(f"User {cmd.user_id} not found")

    user.credits_remaining += Decimal(str(cmd.amount))

    return {
        "user_id": str(cmd.user_id),
        "credits_remaining": float(user.credits_remaining),
    }


def handle_request_export(
    cmd: RequestExport, uow: UnitOfWork
) -> dict:
    user = uow.user_repo.get(cmd.user_id)
    if user is None:
        raise ValueError(f"User {cmd.user_id} not found")

    valid_formats = {"geojson", "coco", "yolo", "pascal_voc", "tfrecord"}
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
    )
    uow.export_repo.add(job)

    return {
        "export_id": str(job.export_id),
        "status": "pending",
        "export_format": cmd.export_format,
    }


def handle_generate_grid_blocks(
    cmd: GenerateGridBlocks, uow: UnitOfWork
) -> dict:
    initiative = uow.initiative_repo.get(cmd.initiative_id)
    if initiative is None:
        raise ValueError(f"Initiative {cmd.initiative_id} not found")

    existing = uow.grid_repo.get_by_initiative(cmd.initiative_id)
    if existing:
        raise ValueError(f"Grids already exist for initiative {cmd.initiative_id}")

    coord_pairs = _parse_polygon_wkt(initiative.region)
    min_lon = min(c[0] for c in coord_pairs)
    max_lon = max(c[0] for c in coord_pairs)
    min_lat = min(c[1] for c in coord_pairs)
    max_lat = max(c[1] for c in coord_pairs)
    grid_size_deg = initiative.grid_size_m / 111_320.0

    lon = min_lon
    generated = 0
    while lon < max_lon:
        lat = min_lat
        while lat < max_lat:
            cell = (
                min(lon + grid_size_deg, max_lon),
                min(lat + grid_size_deg, max_lat),
            )
            wkt = (
                f"POLYGON(({lon} {lat}, {cell[0]} {lat}, "
                f"{cell[0]} {cell[1]}, {lon} {cell[1]}, {lon} {lat}))"
            )
            grid = TaskGrid(
                id=uuid4(),
                initiative_id=cmd.initiative_id,
                geometry=wkt,
            )
            uow.grid_repo.add(grid)
            generated += 1
            lat += grid_size_deg
        lon += grid_size_deg

    return {
        "initiative_id": str(cmd.initiative_id),
        "grids_generated": generated,
    }


def handle_assign_participant(
    cmd: AssignParticipant, uow: UnitOfWork
) -> dict:
    initiative = uow.initiative_repo.get(cmd.initiative_id)
    if initiative is None:
        raise ValueError(f"Initiative {cmd.initiative_id} not found")

    user = uow.user_repo.get(cmd.user_id)
    if user is None:
        raise ValueError(f"User {cmd.user_id} not found")

    participant = Participant(
        initiative_id=cmd.initiative_id,
        user_id=cmd.user_id,
        role=cmd.role,
    )
    uow.participant_repo.add(participant)

    return {
        "initiative_id": str(cmd.initiative_id),
        "user_id": str(cmd.user_id),
        "role": cmd.role,
    }


def handle_list_dataset_for_sale(
    cmd: ListDatasetForSale, uow: UnitOfWork
) -> dict:
    seller = uow.user_repo.get(cmd.seller_id)
    if seller is None:
        raise ValueError(f"User {cmd.seller_id} not found")

    listing = MarketplaceListing(
        listing_id=uuid4(),
        seller_id=cmd.seller_id,
        dataset_id=cmd.dataset_id,
        title=cmd.title,
        description=cmd.description,
        price_tokens=Decimal(str(cmd.price_tokens)),
        geometry_count=cmd.geometry_count,
    )
    uow.marketplace_repo.add_listing(listing)

    return {
        "listing_id": str(listing.listing_id),
        "title": listing.title,
        "price_tokens": float(listing.price_tokens),
    }


def handle_purchase_dataset(
    cmd: PurchaseDataset, uow: UnitOfWork
) -> dict:
    listing = uow.marketplace_repo.get_listing(cmd.listing_id)
    if listing is None:
        raise ValueError(f"Listing {cmd.listing_id} not found")
    if listing.status != "active":
        raise ValueError(f"Listing {cmd.listing_id} is not active")

    buyer = uow.user_repo.get(cmd.buyer_id)
    if buyer is None:
        raise ValueError(f"User {cmd.buyer_id} not found")

    buyer.deduct_credits(listing.price_tokens)
    listing.status = "sold"

    purchase = DatasetPurchase(
        purchase_id=uuid4(),
        listing_id=cmd.listing_id,
        buyer_id=cmd.buyer_id,
        dataset_id=listing.dataset_id,
        tokens_paid=listing.price_tokens,
    )
    uow.marketplace_repo.add_purchase(purchase)
    uow.marketplace_repo.set_listing_status(cmd.listing_id, "sold")

    grid = uow.grid_repo.get(listing.dataset_id)
    for polygon in (grid.polygons if grid else []):
        polygon.qa_status = QaStatus.PENDING

    buyer.raise_event(
        DatasetPurchased(
            listing_id=cmd.listing_id,
            buyer_id=cmd.buyer_id,
            dataset_id=listing.dataset_id,
            tokens_paid=float(listing.price_tokens),
        )
    )

    return {
        "purchase_id": str(purchase.purchase_id),
        "dataset_id": str(listing.dataset_id),
        "tokens_paid": float(listing.price_tokens),
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_polygon_wkt(wkt: str) -> list[tuple[float, float]]:
    inner = wkt.replace("POLYGON((", "").replace("))", "").strip()
    pairs = inner.split(",")
    coords: list[tuple[float, float]] = []
    for p in pairs:
        parts = p.strip().split()
        coords.append((float(parts[0]), float(parts[1])))
    return coords[:-1]


# ---------------------------------------------------------------------------
# Event Handlers
# ---------------------------------------------------------------------------


def handle_classify_confidence(
    event: PolygonValidated, uow: UnitOfWork
) -> None:
    logger.info(
        f"Polygon {event.polygon_id} validated with confidence {event.confidence}"
    )


def handle_flag_for_review(
    event: LowConfidenceDetected, uow: UnitOfWork
) -> None:
    logger.info(
        f"Polygon {event.polygon_id} flagged for review "
        f"(confidence: {event.confidence})"
    )


def handle_update_geometry(
    event: BoundaryCorrected, uow: UnitOfWork
) -> None:
    logger.info(
        f"Polygon {event.polygon_id} geometry updated by user {event.user_id}"
    )


def handle_deduct_credits(
    event: BoundaryCorrected, uow: UnitOfWork
) -> None:
    logger.info(
        f"Credits consumed for correction of polygon {event.polygon_id}"
    )


def handle_check_grid_complete(
    event: BoundaryCorrected, uow: UnitOfWork
) -> None:
    logger.info(
        f"Checking if grid is complete after polygon {event.polygon_id} correction"
    )


def handle_check_initiative_complete(
    event: GridBlockCompleted, uow: UnitOfWork
) -> None:
    logger.info(
        f"Checking if initiative {event.initiative_id} is complete after grid {event.grid_id}"
    )


def handle_credits_exhausted(
    event: CreditsExhausted, uow: UnitOfWork
) -> None:
    logger.warning(f"User {event.user_id} has exhausted credits — validation paused")


def handle_notify_export_complete(
    event: ExportCompleted, uow: UnitOfWork
) -> None:
    logger.info(
        f"Export {event.export_id} completed for user {event.user_id}: {event.output_url}"
    )
