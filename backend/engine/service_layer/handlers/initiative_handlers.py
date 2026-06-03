from __future__ import annotations

import logging
from uuid import uuid4

from backend.engine.domain.commands import AssignParticipant, CreateInitiative
from backend.engine.domain.models import Initiative, Participant
from backend.engine.service_layer.unit_of_work import UnitOfWork

logger = logging.getLogger(__name__)


def handle_create_initiative(cmd: CreateInitiative, uow: UnitOfWork) -> dict:
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


def handle_assign_participant(cmd: AssignParticipant, uow: UnitOfWork) -> dict:
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
