from __future__ import annotations

import logging

from backend.engine.adapters.email_sender import ConsoleEmailSender, EmailSender

from .credit_handlers import handle_top_up_credits
from .grid_handlers import (
    handle_approve_grid_block,
    handle_bulk_assign_grid_blocks,
    handle_claim_grid_block,
    handle_dispute_grid_block,
    handle_generate_grid_blocks,
    handle_lock_grid_block,
    handle_submit_grid_block,
    handle_check_grid_complete,
    handle_check_initiative_complete,
)
from .initiative_handlers import handle_assign_participant, handle_create_initiative
from .hackathon_handlers import (
    handle_join_hackathon,
    handle_submit_hackathon_result,
    handle_score_hackathon_submission,
)
from .marketplace_handlers import handle_list_dataset_for_sale, handle_purchase_dataset
from .polygon_handlers import (
    handle_validate_polygon,
    handle_upload_polygon_set,
    handle_correct_boundary,
)
from .event_handlers import (
    handle_classify_confidence,
    handle_credits_exhausted,
    handle_deduct_credits,
    handle_flag_for_review,
    handle_low_confidence_trigger,
    handle_notify_export_complete,
    handle_request_export,
    handle_update_geometry,
)

# Event handlers for new events
logger = logging.getLogger(__name__)

_email_sender: EmailSender = ConsoleEmailSender()


def set_email_sender(sender: EmailSender) -> None:
    global _email_sender
    _email_sender = sender


def handle_grid_locked(event, uow) -> None:
    logger.info(f"Grid {event.grid_id} locked by user {event.user_id}")


def handle_grid_submitted(event, uow) -> None:
    logger.info(f"Grid {event.grid_id} submitted by user {event.user_id}")


def handle_grid_disputed(event, uow) -> None:
    logger.info(f"Grid {event.grid_id} disputed by reviewer {event.reviewer_id}: {event.notes}")


def handle_initiative_completed_notification(event, uow) -> None:
    owner = uow.user_repo.get(event.owner_id)
    if owner is None:
        logger.warning(f"Owner {event.owner_id} not found for notification")
        return
    _email_sender.send(
        to=owner.email,
        subject=f"Initiative {event.initiative_id} completed",
        body=(
            f"Your initiative {event.initiative_id} has been fully completed.\n"
            "All grid blocks have been finished. You can now export the dataset."
        ),
    )


def handle_dataset_purchased_notification(event, uow) -> None:
    buyer = uow.user_repo.get(event.buyer_id)
    listing = uow.marketplace_repo.get_listing(event.listing_id) if hasattr(uow, "marketplace_repo") else None
    seller = None
    if listing is not None:
        seller = uow.user_repo.get(listing.seller_id)

    if buyer:
        _email_sender.send(
            to=buyer.email,
            subject="Your dataset purchase is confirmed",
            body=(
                f"You purchased dataset {event.dataset_id} for {event.tokens_paid} tokens.\n"
                "You can now download it from the exports page."
            ),
        )
    if seller:
        _email_sender.send(
            to=seller.email,
            subject="Your dataset has been sold",
            body=(
                f"Your dataset listing {event.listing_id} was purchased for {event.tokens_paid} tokens.\n"
                "The tokens have been credited to your account."
            ),
        )


def handle_hackathon_joined_notification(event, uow) -> None:
    participant = uow.user_repo.get(event.user_id)
    if participant is None:
        logger.warning(f"User {event.user_id} not found for notification")
        return
    _email_sender.send(
        to=participant.email,
        subject="You've joined a hackathon!",
        body=(
            f"You have joined hackathon initiative {event.initiative_id}.\n"
            "Claim a grid block and start annotating. Good luck!"
        ),
    )


def handle_consensus_reached(event, uow) -> None:
    logger.info(
        f"Consensus reached for polygon {event.polygon_id} "
        f"from {event.annotation_count} annotations — "
        f"merged geometry: {event.merged_geometry[:60]}..."
    )


def handle_hackathon_score_updated(event, uow) -> None:
    entries = uow.leaderboard_repo.list_by_initiative(event.initiative_id)
    entries.sort(key=lambda e: e.score, reverse=True)
    for i, entry in enumerate(entries):
        entry.place = i + 1
        uow.leaderboard_repo.upsert(entry)
    logger.info(
        f"Leaderboard re-ranked for initiative {event.initiative_id} "
        f"after user {event.user_id} scored {event.score}"
    )