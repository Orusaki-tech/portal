from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID


@dataclass(frozen=True)
class Command:
    pass


@dataclass(frozen=True)
class ValidatePolygon(Command):
    grid_id: UUID
    polygon_id: UUID
    imagery_source: str = "naip"
    user_id: UUID | None = None


@dataclass(frozen=True)
class CorrectBoundary(Command):
    grid_id: UUID
    polygon_id: UUID
    user_id: UUID
    new_geometry: str


@dataclass(frozen=True)
class UploadPolygonSet(Command):
    user_id: UUID
    name: str
    geometries: list[str]
    model_version: str | None = None


@dataclass(frozen=True)
class CreateInitiative(Command):
    owner_id: UUID
    name: str
    region: str
    grid_size_m: int = 1000
    budget_credits: Decimal | None = None


@dataclass(frozen=True)
class LockGridBlock(Command):
    grid_id: UUID
    user_id: UUID


@dataclass(frozen=True)
class ClaimGridBlock(Command):
    initiative_id: UUID
    user_id: UUID


@dataclass(frozen=True)
class SubmitGridBlock(Command):
    grid_id: UUID
    user_id: UUID | None = None


@dataclass(frozen=True)
class ApproveGridBlock(Command):
    grid_id: UUID
    reviewer_id: UUID


@dataclass(frozen=True)
class DisputeGridBlock(Command):
    grid_id: UUID
    reviewer_id: UUID
    notes: str = ""


@dataclass(frozen=True)
class BulkAssignGridBlocks(Command):
    grid_ids: list[UUID]
    user_id: UUID


@dataclass(frozen=True)
class TopUpCredits(Command):
    user_id: UUID
    amount: Decimal


@dataclass(frozen=True)
class RequestExport(Command):
    user_id: UUID
    export_format: str
    source_type: str
    source_id: UUID
    qa_status: str | None = None
    confidence_min: float | None = None
    confidence_max: float | None = None
    annotator_id: UUID | None = None
    include_original: bool = True


@dataclass(frozen=True)
class GenerateGridBlocks(Command):
    initiative_id: UUID


@dataclass(frozen=True)
class AssignParticipant(Command):
    initiative_id: UUID
    user_id: UUID
    role: str = "annotator"


@dataclass(frozen=True)
class ListDatasetForSale(Command):
    seller_id: UUID
    dataset_id: UUID
    title: str
    price_tokens: Decimal
    geometry_count: int = 0
    description: str | None = None


@dataclass(frozen=True)
class PurchaseDataset(Command):
    listing_id: UUID
    buyer_id: UUID


@dataclass(frozen=True)
class JoinHackathon(Command):
    initiative_id: UUID
    user_id: UUID


@dataclass(frozen=True)
class SubmitHackathonResult(Command):
    initiative_id: UUID
    user_id: UUID
    score: float
    accuracy_pct: float


@dataclass(frozen=True)
class ScoreHackathonSubmission(Command):
    initiative_id: UUID
    submission_id: UUID
    score: float
