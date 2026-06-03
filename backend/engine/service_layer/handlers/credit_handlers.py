from __future__ import annotations

import logging
from typing import Any
from uuid import uuid4

from backend.engine.domain.commands import TopUpCredits
from backend.engine.domain.models import CreditTransaction
from backend.engine.service_layer.unit_of_work import UnitOfWork

logger = logging.getLogger(__name__)


def handle_top_up_credits(cmd: TopUpCredits, uow: UnitOfWork) -> dict[str, Any]:
    user = uow.user_repo.get(cmd.user_id)
    if user is None:
        raise ValueError(f"User {cmd.user_id} not found")

    user.credits_remaining += cmd.amount
    uow.credit_txn_repo.add(
        CreditTransaction(
            id=uuid4(),
            user_id=cmd.user_id,
            amount=cmd.amount,
            transaction_type="top_up",
            description=f"Manual top-up of {cmd.amount} credits",
        )
    )

    return {
        "user_id": str(cmd.user_id),
        "credits_remaining": float(user.credits_remaining),
    }
