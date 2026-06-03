from __future__ import annotations

import logging
from uuid import uuid4

from backend.engine.domain.commands import ListDatasetForSale, PurchaseDataset
from backend.engine.domain.events import DatasetPurchased
from backend.engine.domain.models import DatasetPurchase, MarketplaceListing, QaStatus
from backend.engine.service_layer.unit_of_work import UnitOfWork

logger = logging.getLogger(__name__)


def handle_list_dataset_for_sale(cmd: ListDatasetForSale, uow: UnitOfWork) -> dict:
    seller = uow.user_repo.get(cmd.seller_id)
    if seller is None:
        raise ValueError(f"User {cmd.seller_id} not found")

    grid = uow.grid_repo.get(cmd.dataset_id)
    polygons = grid.polygons if grid else []
    polygon_count = len(polygons)

    confidences = [p.confidence_avg for p in polygons if p.confidence_avg is not None]
    quality_score = (sum(confidences) / len(confidences)) if confidences else None

    completed = [p for p in polygons if p.qa_status in (QaStatus.VALIDATED, QaStatus.REVIEWED)]
    completion_rate = (len(completed) / polygon_count) if polygon_count > 0 else None

    listing = MarketplaceListing(
        listing_id=uuid4(),
        seller_id=cmd.seller_id,
        dataset_id=cmd.dataset_id,
        title=cmd.title,
        description=cmd.description,
        price_tokens=cmd.price_tokens,
        geometry_count=cmd.geometry_count or polygon_count,
        quality_score=quality_score,
        completion_rate=completion_rate,
    )
    uow.marketplace_repo.add_listing(listing)

    return {
        "listing_id": str(listing.listing_id),
        "title": listing.title,
        "price_tokens": float(listing.price_tokens),
        "quality_score": quality_score,
        "completion_rate": completion_rate,
    }


def handle_purchase_dataset(cmd: PurchaseDataset, uow: UnitOfWork) -> dict:
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
    for polygon in grid.polygons if grid else []:
        polygon.qa_status = QaStatus.PENDING

    buyer.raise_event(
        DatasetPurchased(
            listing_id=cmd.listing_id,
            buyer_id=cmd.buyer_id,
            dataset_id=listing.dataset_id,
            tokens_paid=listing.price_tokens,
        )
    )

    return {
        "purchase_id": str(purchase.purchase_id),
        "dataset_id": str(listing.dataset_id),
        "tokens_paid": float(listing.price_tokens),
    }
