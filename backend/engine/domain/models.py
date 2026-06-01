from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

UTC = timezone.utc
from decimal import Decimal
from enum import Enum
from uuid import UUID, uuid4

from backend.engine.domain.events import (
    CreditsExhausted,
    Event,
    GridBlockCompleted,
)


class QaStatus(str, Enum):
    PENDING = "pending"
    VALIDATED = "validated"
    LOW_CONFIDENCE = "low_confidence"
    CORRECTED = "corrected"
    ESCALATED = "escalated"


class GridStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    AWAITING_REVIEW = "awaiting_review"
    COMPLETE = "complete"
    DISPUTED = "disputed"


class InitiativeStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETE = "complete"
    ARCHIVED = "archived"


@dataclass(frozen=True)
class Coordinate:
    longitude: float
    latitude: float


@dataclass(frozen=True)
class VertexMetric:
    vertex_index: int
    deviation_meters: float
    spectral_contrast: float
    snake_strain: float
    confidence_score: float


@dataclass(frozen=True)
class ConfidenceScore:
    overall: float
    per_vertex: list[VertexMetric]

    def __post_init__(self) -> None:
        if not (0.0 <= self.overall <= 1.0):
            raise ValueError(f"Confidence must be 0.0–1.0, got {self.overall}")
        for v in self.per_vertex:
            if not (0.0 <= v.confidence_score <= 1.0):
                raise ValueError(
                    f"Per-vertex confidence must be 0.0–1.0, got {v.confidence_score}"
                )


@dataclass
class Polygon:
    id: UUID
    task_grid_id: UUID | None
    polygon_set_id: UUID
    original_geometry: str
    qa_status: QaStatus = QaStatus.PENDING
    confidence_avg: float | None = None
    corrected_geometry: str | None = None
    properties: dict | None = None

    def __post_init__(self) -> None:
        self.properties = self.properties or {}

    def validate(self, confidence_score: ConfidenceScore, threshold: float = 0.70) -> None:
        self.confidence_avg = confidence_score.overall
        if confidence_score.overall >= threshold:
            self.qa_status = QaStatus.VALIDATED
        else:
            self.qa_status = QaStatus.LOW_CONFIDENCE

    def correct(self, new_geometry: str) -> None:
        self.corrected_geometry = new_geometry
        self.qa_status = QaStatus.CORRECTED

    def escalate(self) -> None:
        self.qa_status = QaStatus.ESCALATED


@dataclass
class TaskGrid:
    id: UUID
    initiative_id: UUID
    geometry: str
    status: GridStatus = GridStatus.PENDING
    assigned_user_id: UUID | None = None
    locked_at: datetime | None = None
    completed_at: datetime | None = None
    review_notes: str | None = None
    polygons: list[Polygon] = field(default_factory=list)
    _events: list[Event] = field(default_factory=list)

    def assign_to(self, user_id: UUID) -> None:
        if self.assigned_user_id is not None and self.assigned_user_id != user_id:
            raise ValueError(
                f"Grid {self.id} is already assigned to {self.assigned_user_id}"
            )
        self.assigned_user_id = user_id

    def lock(self, user_id: UUID) -> None:
        if self.status == GridStatus.COMPLETE:
            raise ValueError(f"Cannot lock completed grid {self.id}")
        if self.status == GridStatus.IN_PROGRESS:
            raise ValueError(f"Grid {self.id} is already locked")
        if self.assigned_user_id is not None and self.assigned_user_id != user_id:
            raise ValueError(
                f"Grid {self.id} is assigned to another user ({self.assigned_user_id})"
            )
        self.status = GridStatus.IN_PROGRESS
        self.assigned_user_id = user_id
        self.locked_at = datetime.now(UTC)

    def release(self) -> None:
        self.status = GridStatus.PENDING
        self.assigned_user_id = None
        self.locked_at = None

    def submit_review(self) -> None:
        if self.status != GridStatus.IN_PROGRESS:
            raise ValueError(
                f"Cannot submit review for grid {self.id} in status {self.status}"
            )
        self.status = GridStatus.AWAITING_REVIEW

    def complete(self) -> None:
        if self.status == GridStatus.COMPLETE:
            raise ValueError(f"Grid {self.id} is already complete")
        self.status = GridStatus.COMPLETE
        self.completed_at = datetime.now(UTC)
        self._events.append(
            GridBlockCompleted(grid_id=self.id, initiative_id=self.initiative_id)
        )

    def dispute(self, notes: str) -> None:
        self.status = GridStatus.DISPUTED
        self.review_notes = notes

    def raise_event(self, event: Event) -> None:
        self._events.append(event)

    @property
    def events(self) -> list[Event]:
        return self._events

    def clear_events(self) -> None:
        self._events = []


@dataclass
class User:
    id: UUID
    email: str
    name: str
    role: str
    credits_remaining: Decimal = Decimal("0")
    _events: list[Event] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.credits_remaining < Decimal("0"):
            raise ValueError("Credits remaining must be non-negative")

    def deduct_credits(self, amount: Decimal) -> None:
        if amount > self.credits_remaining:
            raise ValueError(
                f"Insufficient credits: {self.credits_remaining} < {amount}"
            )
        self.credits_remaining -= amount
        if self.credits_remaining == 0:
            self._events.append(CreditsExhausted(user_id=self.id))

    def raise_event(self, event: Event) -> None:
        self._events.append(event)

    @property
    def events(self) -> list[Event]:
        return self._events

    def clear_events(self) -> None:
        self._events = []


@dataclass
class Initiative:
    id: UUID
    owner_id: UUID
    name: str
    region: str
    status: InitiativeStatus = InitiativeStatus.DRAFT
    grid_size_m: int = 1000
    budget_credits: Decimal | None = None
    created_at: datetime | None = None
    completed_at: datetime | None = None

    def activate(self) -> None:
        if self.status != InitiativeStatus.DRAFT:
            raise ValueError(f"Cannot activate initiative in status {self.status}")
        self.status = InitiativeStatus.ACTIVE

    def complete(self) -> None:
        self.status = InitiativeStatus.COMPLETE
        self.completed_at = datetime.now(UTC)

    def archive(self) -> None:
        self.status = InitiativeStatus.ARCHIVED


@dataclass
class Correction:
    id: UUID
    polygon_id: UUID
    user_id: UUID
    original_geometry: str
    corrected_geometry: str
    action: str = "correct"
    notes: str | None = None
    created_at: datetime | None = None


@dataclass
class ExportJob:
    export_id: UUID
    user_id: UUID
    export_format: str
    source_type: str
    source_id: UUID
    status: str = "pending"
    output_url: str | None = None
    error_message: str | None = None
    created_at: datetime | None = None
    completed_at: datetime | None = None


@dataclass
class Participant:
    initiative_id: UUID
    user_id: UUID
    role: str = "annotator"
    joined_at: datetime | None = None


@dataclass
class MarketplaceListing:
    listing_id: UUID
    seller_id: UUID
    dataset_id: UUID
    title: str
    price_tokens: Decimal
    geometry_count: int = 0
    description: str | None = None
    status: str = "active"
    created_at: datetime | None = None


@dataclass
class DatasetPurchase:
    purchase_id: UUID
    listing_id: UUID
    buyer_id: UUID
    dataset_id: UUID
    tokens_paid: Decimal
    purchased_at: datetime | None = None
