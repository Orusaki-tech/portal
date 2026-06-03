from __future__ import annotations

import logging
from uuid import uuid4

from backend.engine.domain.commands import (
    JoinHackathon,
    ScoreHackathonSubmission,
    SubmitHackathonResult,
)
from backend.engine.domain.events import HackathonJoined, HackathonScoreUpdated
from backend.engine.domain.models import LeaderboardEntry
from backend.engine.service_layer.unit_of_work import UnitOfWork

logger = logging.getLogger(__name__)


def handle_join_hackathon(cmd: JoinHackathon, uow: UnitOfWork) -> None:
    initiative = uow.initiative_repo.get(cmd.initiative_id)
    if initiative is None:
        raise ValueError(f"Initiative {cmd.initiative_id} not found")
    if not initiative.hackathon_mode:
        raise ValueError(f"Initiative {cmd.initiative_id} is not a hackathon")
    if initiative.max_participants:
        existing = uow.leaderboard_repo.list_by_initiative(cmd.initiative_id)
        if len(existing) >= initiative.max_participants:
            raise ValueError(f"Hackathon {cmd.initiative_id} is full")

    entry = uow.leaderboard_repo.get_by_user_and_initiative(cmd.initiative_id, cmd.user_id)
    if entry is not None:
        raise ValueError(f"User {cmd.user_id} already joined this hackathon")

    entry = LeaderboardEntry(
        id=uuid4(),
        initiative_id=cmd.initiative_id,
        user_id=cmd.user_id,
    )
    entry.raise_event(HackathonJoined(initiative_id=cmd.initiative_id, user_id=cmd.user_id))
    uow.leaderboard_repo.upsert(entry)


def handle_submit_hackathon_result(cmd: SubmitHackathonResult, uow: UnitOfWork) -> None:
    entry = uow.leaderboard_repo.get_by_user_and_initiative(cmd.initiative_id, cmd.user_id)
    if entry is None:
        raise ValueError(f"User {cmd.user_id} has not joined hackathon {cmd.initiative_id}")

    entry.submit_result(cmd.score, cmd.accuracy_pct)
    entry.raise_event(HackathonScoreUpdated(
        initiative_id=cmd.initiative_id,
        user_id=cmd.user_id,
        score=cmd.score,
    ))
    uow.leaderboard_repo.upsert(entry)


def handle_score_hackathon_submission(cmd: ScoreHackathonSubmission, uow: UnitOfWork) -> None:
    entries = uow.leaderboard_repo.list_by_initiative(cmd.initiative_id)
    target = next((e for e in entries if e.id == cmd.submission_id), None)
    if target is None:
        raise ValueError(f"Submission {cmd.submission_id} not found in hackathon {cmd.initiative_id}")

    target.update_score(cmd.score, target.accuracy_pct)
    target.raise_event(HackathonScoreUpdated(
        initiative_id=cmd.initiative_id,
        user_id=target.user_id,
        score=cmd.score,
    ))
    uow.leaderboard_repo.upsert(target)