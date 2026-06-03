from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from uuid import UUID

from shapely import wkt

from backend.engine.domain.events import (
    CreditsExhausted,
    Event,
    GridBlockCompleted,
)


class QaStatus(Enum):
    PENDING = "pending"
    VALIDATED = "validated"
    LOW_CONFIDENCE = "low_confidence"
    CORRECTED = "corrected"
    ESCALATED = "escalated"


class GridStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    AWAITING_REVIEW = "awaiting_review"
    COMPLETE = "complete"
    DISPUTED = "disputed"


class InitiativeStatus(Enum):
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
                raise ValueError(f"Per-vertex confidence must be 0.0–1.0, got {v.confidence_score}")


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
        try:
            wkt.loads(self.original_geometry)
        except Exception as e:
            raise ValueError(f"Invalid original_geometry WKT: {e}")

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

    _transitions: dict[GridStatus, set[GridStatus]] = field(
        default_factory=lambda: {
            GridStatus.PENDING: {GridStatus.IN_PROGRESS},
            GridStatus.IN_PROGRESS: {GridStatus.AWAITING_REVIEW, GridStatus.PENDING},
            GridStatus.AWAITING_REVIEW: {GridStatus.COMPLETE, GridStatus.DISPUTED},
            GridStatus.DISPUTED: {GridStatus.PENDING},
            GridStatus.COMPLETE: set(),
        },
        repr=False,
    )

    def __post_init__(self) -> None:
        try:
            wkt.loads(self.geometry)
        except Exception as e:
            raise ValueError(f"Invalid geometry WKT: {e}")

    def _transition_to(self, new_status: GridStatus) -> None:
        allowed = self._transitions.get(self.status, set())
        if new_status not in allowed:
            raise ValueError(
                f"Cannot transition grid {self.id} from {self.status.value} to {new_status.value}"
            )
        self.status = new_status

    def assign_to(self, user_id: UUID) -> None:
        if self.assigned_user_id is not None and self.assigned_user_id != user_id:
            raise ValueError(f"Grid {self.id} is already assigned to {self.assigned_user_id}")
        self.assigned_user_id = user_id

    def lock(self, user_id: UUID) -> None:
        self._transition_to(GridStatus.IN_PROGRESS)
        if self.assigned_user_id is not None and self.assigned_user_id != user_id:
            raise ValueError(
                f"Grid {self.id} is assigned to another user ({self.assigned_user_id})"
            )
        self.assigned_user_id = user_id
        self.locked_at = datetime.now(UTC)

    def release(self) -> None:
        self._transition_to(GridStatus.PENDING)
        self.assigned_user_id = None
        self.locked_at = None

    def submit_review(self) -> None:
        self._transition_to(GridStatus.AWAITING_REVIEW)

    def complete(self) -> None:
        self._transition_to(GridStatus.COMPLETE)
        self.completed_at = datetime.now(UTC)
        self._events.append(GridBlockCompleted(grid_id=self.id, initiative_id=self.initiative_id))

    def dispute(self, notes: str) -> None:
        self._transition_to(GridStatus.DISPUTED)
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
    subscription_tier: str = "free"
    api_key: str | None = None
    _events: list[Event] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.credits_remaining < Decimal("0"):
            raise ValueError("Credits remaining must be non-negative")
        if "@" not in self.email:
            raise ValueError(f"Invalid email: {self.email}")
        valid_roles = {"admin", "annotator", "reviewer", "senior_reviewer", "manager", "viewer"}
        if self.role not in valid_roles:
            raise ValueError(f"Invalid role '{self.role}'; must be one of {valid_roles}")
        valid_tiers = {"free", "starter", "professional"}
        if self.subscription_tier not in valid_tiers:
            raise ValueError(
                f"Invalid subscription_tier '{self.subscription_tier}'; must be one of {valid_tiers}"  # noqa: E501
            )

    def deduct_credits(self, amount: Decimal) -> None:
        if amount > self.credits_remaining:
            raise ValueError(f"Insufficient credits: {self.credits_remaining} < {amount}")
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
    hackathon_mode: bool = False
    max_participants: int | None = None
    created_at: datetime | None = None
    completed_at: datetime | None = None
    _events: list[Event] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.grid_size_m <= 0:
            raise ValueError(f"grid_size_m must be positive, got {self.grid_size_m}")
        if self.budget_credits is not None and self.budget_credits < Decimal("0"):
            raise ValueError(f"budget_credits must be non-negative, got {self.budget_credits}")
        if self.max_participants is not None and self.max_participants < 1:
            raise ValueError(f"max_participants must be >= 1, got {self.max_participants}")
        try:
            wkt.loads(self.region)
        except Exception as e:
            raise ValueError(f"Invalid region WKT: {e}")

    def raise_event(self, event: Event) -> None:
        self._events.append(event)

    @property
    def events(self) -> list[Event]:
        ret = self._events[:]
        self._events = []
        return ret

    def clear_events(self) -> None:
        self._events = []

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

    def __post_init__(self) -> None:
        valid_actions = {"correct", "refine", "reset"}
        if self.action not in valid_actions:
            raise ValueError(f"Invalid action '{self.action}'; must be one of {valid_actions}")
        try:
            wkt.loads(self.original_geometry)
        except Exception as e:
            raise ValueError(f"Invalid original_geometry WKT: {e}")
        try:
            wkt.loads(self.corrected_geometry)
        except Exception as e:
            raise ValueError(f"Invalid corrected_geometry WKT: {e}")
        if self.created_at is None:
            self.created_at = datetime.now(UTC)


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
    export_params: dict | None = None
    created_at: datetime | None = None
    completed_at: datetime | None = None

    _valid_formats = frozenset(
        {"geojson", "coco", "yolo", "pascal_voc", "tfrecord", "parquet", "geopackage"}
    )
    _valid_source_types = frozenset({"dataset", "initiative", "grid"})

    def __post_init__(self) -> None:
        if self.export_format not in self._valid_formats:
            raise ValueError(f"Invalid export_format '{self.export_format}'")
        if self.source_type not in self._valid_source_types:
            raise ValueError(f"Invalid source_type '{self.source_type}'")


@dataclass
class Participant:
    initiative_id: UUID
    user_id: UUID
    role: str = "annotator"
    joined_at: datetime | None = None

    def __post_init__(self) -> None:
        valid_roles = {"annotator", "reviewer", "manager", "owner"}
        if self.role not in valid_roles:
            raise ValueError(f"Invalid role '{self.role}'; must be one of {valid_roles}")


@dataclass
class MarketplaceListing:
    listing_id: UUID
    seller_id: UUID
    dataset_id: UUID
    title: str
    price_tokens: Decimal
    geometry_count: int = 0
    quality_score: float | None = None
    completion_rate: float | None = None
    description: str | None = None
    status: str = "active"
    created_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.price_tokens < Decimal("0"):
            raise ValueError(f"price_tokens must be non-negative, got {self.price_tokens}")
        if self.geometry_count < 0:
            raise ValueError(f"geometry_count must be non-negative, got {self.geometry_count}")
        if self.quality_score is not None and not (0.0 <= self.quality_score <= 1.0):
            raise ValueError(f"quality_score must be 0.0–1.0, got {self.quality_score}")
        if self.completion_rate is not None and not (0.0 <= self.completion_rate <= 1.0):
            raise ValueError(f"completion_rate must be 0.0–1.0, got {self.completion_rate}")
        valid_statuses = {"active", "sold", "archived"}
        if self.status not in valid_statuses:
            raise ValueError(f"Invalid status '{self.status}'")


@dataclass
class PolygonSet:
    id: UUID
    user_id: UUID
    name: str
    model_version: str | None = None
    description: str | None = None
    created_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("PolygonSet name must not be empty")


@dataclass
class DatasetPurchase:
    purchase_id: UUID
    listing_id: UUID
    buyer_id: UUID
    dataset_id: UUID
    tokens_paid: Decimal
    purchased_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.tokens_paid < Decimal("0"):
            raise ValueError(f"tokens_paid must be non-negative, got {self.tokens_paid}")


@dataclass
class CreditTransaction:
    id: UUID
    user_id: UUID
    amount: Decimal
    transaction_type: str
    reference_id: UUID | None = None
    description: str | None = None
    created_at: datetime | None = None

    def __post_init__(self) -> None:
        valid_types = {"top_up", "validation", "correction", "purchase", "refund"}
        if self.transaction_type not in valid_types:
            raise ValueError(f"Invalid transaction_type '{self.transaction_type}'")
        if self.created_at is None:
            self.created_at = datetime.now(UTC)


@dataclass
class ValidationRun:
    id: UUID
    user_id: UUID
    polygon_set_id: UUID
    polygon_count: int = 0
    ambiguous_count: int = 0
    cost_credits: Decimal = Decimal("0")
    status: str = "queued"
    imagery_id: UUID | None = None
    region: str | None = None
    created_at: datetime | None = None
    completed_at: datetime | None = None

    _valid_statuses = frozenset({"queued", "processing", "complete", "failed"})

    def __post_init__(self) -> None:
        if self.status not in self._valid_statuses:
            raise ValueError(f"Invalid status '{self.status}'")
        if self.cost_credits < Decimal("0"):
            raise ValueError(f"cost_credits must be non-negative, got {self.cost_credits}")
        if self.polygon_count < 0:
            raise ValueError(f"polygon_count must be non-negative, got {self.polygon_count}")
        if self.ambiguous_count < 0:
            raise ValueError(f"ambiguous_count must be non-negative, got {self.ambiguous_count}")
        if self.region is not None:
            from shapely import wkt as shapely_wkt

            try:
                shapely_wkt.loads(self.region)
            except Exception as e:
                raise ValueError(f"Invalid region WKT: {e}")


@dataclass
class LeaderboardEntry:
    id: UUID
    initiative_id: UUID
    user_id: UUID
    score: float = 0.0
    polygons_submitted: int = 0
    accuracy_pct: float = 0.0
    place: int | None = None
    submitted_at: datetime | None = None
    _events: list[Event] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not (0.0 <= self.score <= 1.0):
            raise ValueError(f"score must be 0.0–1.0, got {self.score}")
        if not (0.0 <= self.accuracy_pct <= 100.0):
            raise ValueError(f"accuracy_pct must be 0.0–100.0, got {self.accuracy_pct}")
        if self.polygons_submitted < 0:
            raise ValueError(
                f"polygons_submitted must be non-negative, got {self.polygons_submitted}"
            )

    def submit_result(self, new_score: float, accuracy_pct: float) -> None:
        self.score = new_score
        self.accuracy_pct = accuracy_pct
        self.polygons_submitted += 1
        self.submitted_at = datetime.now(UTC)

    def update_score(self, new_score: float, accuracy_pct: float) -> None:
        self.score = new_score
        self.accuracy_pct = accuracy_pct
        self.submitted_at = datetime.now(UTC)

    def raise_event(self, event: Event) -> None:
        self._events.append(event)

    @property
    def events(self) -> list[Event]:
        return self._events

    def clear_events(self) -> None:
        self._events = []
