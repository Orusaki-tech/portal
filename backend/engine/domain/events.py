from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4


@dataclass(frozen=True)
class Event:
    event_id: UUID
    timestamp: datetime


@dataclass(frozen=True)
class PolygonValidated(Event):
    polygon_id: UUID
    confidence: float
    is_ambiguous: bool

    def __init__(self, polygon_id: UUID, confidence: float, is_ambiguous: bool) -> None:
        object.__setattr__(self, "event_id", uuid4())
        object.__setattr__(self, "timestamp", datetime.now(timezone.utc))
        object.__setattr__(self, "polygon_id", polygon_id)
        object.__setattr__(self, "confidence", confidence)
        object.__setattr__(self, "is_ambiguous", is_ambiguous)


@dataclass(frozen=True)
class LowConfidenceDetected(Event):
    polygon_id: UUID
    confidence: float

    def __init__(self, polygon_id: UUID, confidence: float) -> None:
        object.__setattr__(self, "event_id", uuid4())
        object.__setattr__(self, "timestamp", datetime.now(timezone.utc))
        object.__setattr__(self, "polygon_id", polygon_id)
        object.__setattr__(self, "confidence", confidence)


@dataclass(frozen=True)
class BoundaryCorrected(Event):
    polygon_id: UUID
    user_id: UUID
    new_geometry: str

    def __init__(self, polygon_id: UUID, user_id: UUID, new_geometry: str) -> None:
        object.__setattr__(self, "event_id", uuid4())
        object.__setattr__(self, "timestamp", datetime.now(timezone.utc))
        object.__setattr__(self, "polygon_id", polygon_id)
        object.__setattr__(self, "user_id", user_id)
        object.__setattr__(self, "new_geometry", new_geometry)


@dataclass(frozen=True)
class GridBlockLocked(Event):
    grid_id: UUID
    user_id: UUID

    def __init__(self, grid_id: UUID, user_id: UUID) -> None:
        object.__setattr__(self, "event_id", uuid4())
        object.__setattr__(self, "timestamp", datetime.now(timezone.utc))
        object.__setattr__(self, "grid_id", grid_id)
        object.__setattr__(self, "user_id", user_id)


@dataclass(frozen=True)
class GridBlockSubmitted(Event):
    grid_id: UUID
    user_id: UUID

    def __init__(self, grid_id: UUID, user_id: UUID) -> None:
        object.__setattr__(self, "event_id", uuid4())
        object.__setattr__(self, "timestamp", datetime.now(timezone.utc))
        object.__setattr__(self, "grid_id", grid_id)
        object.__setattr__(self, "user_id", user_id)


@dataclass(frozen=True)
class GridBlockDisputed(Event):
    grid_id: UUID
    reviewer_id: UUID
    notes: str

    def __init__(self, grid_id: UUID, reviewer_id: UUID, notes: str) -> None:
        object.__setattr__(self, "event_id", uuid4())
        object.__setattr__(self, "timestamp", datetime.now(timezone.utc))
        object.__setattr__(self, "grid_id", grid_id)
        object.__setattr__(self, "reviewer_id", reviewer_id)
        object.__setattr__(self, "notes", notes)


@dataclass(frozen=True)
class GridBlockCompleted(Event):
    grid_id: UUID
    initiative_id: UUID

    def __init__(self, grid_id: UUID, initiative_id: UUID) -> None:
        object.__setattr__(self, "event_id", uuid4())
        object.__setattr__(self, "timestamp", datetime.now(timezone.utc))
        object.__setattr__(self, "grid_id", grid_id)
        object.__setattr__(self, "initiative_id", initiative_id)


@dataclass(frozen=True)
class InitiativeCompleted(Event):
    initiative_id: UUID
    owner_id: UUID

    def __init__(self, initiative_id: UUID, owner_id: UUID) -> None:
        object.__setattr__(self, "event_id", uuid4())
        object.__setattr__(self, "timestamp", datetime.now(timezone.utc))
        object.__setattr__(self, "initiative_id", initiative_id)
        object.__setattr__(self, "owner_id", owner_id)


@dataclass(frozen=True)
class CreditsExhausted(Event):
    user_id: UUID

    def __init__(self, user_id: UUID) -> None:
        object.__setattr__(self, "event_id", uuid4())
        object.__setattr__(self, "timestamp", datetime.now(timezone.utc))
        object.__setattr__(self, "user_id", user_id)


@dataclass(frozen=True)
class ExportCompleted(Event):
    export_id: UUID
    user_id: UUID
    format: str
    output_url: str

    def __init__(self, export_id: UUID, user_id: UUID, format: str, output_url: str) -> None:
        object.__setattr__(self, "event_id", uuid4())
        object.__setattr__(self, "timestamp", datetime.now(timezone.utc))
        object.__setattr__(self, "export_id", export_id)
        object.__setattr__(self, "user_id", user_id)
        object.__setattr__(self, "format", format)
        object.__setattr__(self, "output_url", output_url)


@dataclass(frozen=True)
class ConsensusReached(Event):
    polygon_id: UUID
    merged_geometry: str
    annotation_count: int

    def __init__(self, polygon_id: UUID, merged_geometry: str, annotation_count: int) -> None:
        object.__setattr__(self, "event_id", uuid4())
        object.__setattr__(self, "timestamp", datetime.now(timezone.utc))
        object.__setattr__(self, "polygon_id", polygon_id)
        object.__setattr__(self, "merged_geometry", merged_geometry)
        object.__setattr__(self, "annotation_count", annotation_count)


@dataclass(frozen=True)
class DatasetPurchased(Event):
    listing_id: UUID
    buyer_id: UUID
    dataset_id: UUID
    tokens_paid: Decimal

    def __init__(self, listing_id: UUID, buyer_id: UUID, dataset_id: UUID, tokens_paid: Decimal) -> None:
        object.__setattr__(self, "event_id", uuid4())
        object.__setattr__(self, "timestamp", datetime.now(timezone.utc))
        object.__setattr__(self, "listing_id", listing_id)
        object.__setattr__(self, "buyer_id", buyer_id)
        object.__setattr__(self, "dataset_id", dataset_id)
        object.__setattr__(self, "tokens_paid", tokens_paid)


@dataclass(frozen=True)
class HackathonJoined(Event):
    initiative_id: UUID
    user_id: UUID

    def __init__(self, initiative_id: UUID, user_id: UUID) -> None:
        object.__setattr__(self, "event_id", uuid4())
        object.__setattr__(self, "timestamp", datetime.now(timezone.utc))
        object.__setattr__(self, "initiative_id", initiative_id)
        object.__setattr__(self, "user_id", user_id)


@dataclass(frozen=True)
class HackathonScoreUpdated(Event):
    initiative_id: UUID
    user_id: UUID
    score: float

    def __init__(self, initiative_id: UUID, user_id: UUID, score: float) -> None:
        object.__setattr__(self, "event_id", uuid4())
        object.__setattr__(self, "timestamp", datetime.now(timezone.utc))
        object.__setattr__(self, "initiative_id", initiative_id)
        object.__setattr__(self, "user_id", user_id)
        object.__setattr__(self, "score", score)
