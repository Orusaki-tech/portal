from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

import psycopg2
import psycopg2.extras

from backend.engine.domain.models import (
    Correction,
    DatasetPurchase,
    ExportJob,
    GridStatus,
    Initiative,
    InitiativeStatus,
    MarketplaceListing,
    Participant,
    Polygon,
    QaStatus,
    TaskGrid,
    User,
)

psycopg2.extras.register_uuid()


class AbstractTaskGridRepository(ABC):
    @abstractmethod
    def add(self, grid: TaskGrid) -> None: ...

    @abstractmethod
    def get(self, grid_id: UUID) -> TaskGrid | None: ...

    @abstractmethod
    def get_by_initiative(self, initiative_id: UUID) -> list[TaskGrid]: ...

    @abstractmethod
    def list_by_status(self, status: str) -> list[TaskGrid]: ...


class AbstractUserRepository(ABC):
    @abstractmethod
    def add(self, user: User) -> None: ...

    @abstractmethod
    def get(self, user_id: UUID) -> User | None: ...

    @abstractmethod
    def get_by_email(self, email: str) -> User | None: ...


class AbstractInitiativeRepository(ABC):
    @abstractmethod
    def add(self, initiative: Initiative) -> None: ...

    @abstractmethod
    def get(self, initiative_id: UUID) -> Initiative | None: ...


class AbstractCorrectionRepository(ABC):
    @abstractmethod
    def add(self, correction: Correction) -> None: ...

    @abstractmethod
    def get_by_polygon(self, polygon_id: UUID) -> list[Correction]: ...


class AbstractExportRepository(ABC):
    @abstractmethod
    def add(self, job: ExportJob) -> None: ...

    @abstractmethod
    def get(self, export_id: UUID) -> ExportJob | None: ...

    @abstractmethod
    def list_by_user(self, user_id: UUID) -> list[ExportJob]: ...


class AbstractParticipantRepository(ABC):
    @abstractmethod
    def add(self, participant: Participant) -> None: ...

    @abstractmethod
    def list_by_initiative(self, initiative_id: UUID) -> list[Participant]: ...

    @abstractmethod
    def list_by_user(self, user_id: UUID) -> list[Participant]: ...


class AbstractMarketplaceRepository(ABC):
    @abstractmethod
    def add_listing(self, listing: MarketplaceListing) -> None: ...

    @abstractmethod
    def get_listing(self, listing_id: UUID) -> MarketplaceListing | None: ...

    @abstractmethod
    def list_active(self) -> list[MarketplaceListing]: ...

    @abstractmethod
    def add_purchase(self, purchase: DatasetPurchase) -> None: ...

    @abstractmethod
    def set_listing_status(self, listing_id: UUID, status: str) -> None: ...


class FakeTaskGridRepository(AbstractTaskGridRepository):
    def __init__(self) -> None:
        self._grids: dict[UUID, TaskGrid] = {}

    def add(self, grid: TaskGrid) -> None:
        self._grids[grid.id] = grid

    def get(self, grid_id: UUID) -> TaskGrid | None:
        return self._grids.get(grid_id)

    def get_by_initiative(self, initiative_id: UUID) -> list[TaskGrid]:
        return [g for g in self._grids.values() if g.initiative_id == initiative_id]

    def list_by_status(self, status: str) -> list[TaskGrid]:
        return [g for g in self._grids.values() if g.status.value == status]


class PostgresTaskGridRepository(AbstractTaskGridRepository):
    def __init__(self, conn: psycopg2.extensions.connection) -> None:
        self.conn = conn
        self.seen: dict[UUID, TaskGrid] = {}

    def add(self, grid: TaskGrid) -> None:
        self.seen[grid.id] = grid
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO map_task_grid (grid_id, initiative_id, geometry, status,
                                           assigned_user_id, locked_at, completed_at, review_notes)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    grid.id, grid.initiative_id, grid.geometry,
                    grid.status.value, grid.assigned_user_id,
                    grid.locked_at, grid.completed_at, grid.review_notes,
                ),
            )
            for polygon in grid.polygons:
                cur.execute(
                    """
                    INSERT INTO ml_polygons (id, polygon_set_id, task_grid_id,
                                             original_geometry, qa_status,
                                             confidence_avg, corrected_geometry, properties)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        polygon.id, polygon.polygon_set_id, polygon.task_grid_id,
                        polygon.original_geometry,
                        polygon.qa_status.value, polygon.confidence_avg,
                        polygon.corrected_geometry,
                        psycopg2.extras.Json(polygon.properties or {}),
                    ),
                )

    def get(self, grid_id: UUID) -> TaskGrid | None:
        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM map_task_grid WHERE grid_id = %s",
                (grid_id,),
            )
            row = cur.fetchone()
            if row is None:
                return None

            grid = self._row_to_grid(row)

            cur.execute(
                "SELECT * FROM ml_polygons WHERE task_grid_id = %s",
                (grid_id,),
            )
            for p_row in cur.fetchall():
                grid.polygons.append(self._row_to_polygon(p_row))

            self.seen[grid.id] = grid
            return grid

    def get_by_initiative(self, initiative_id: UUID) -> list[TaskGrid]:
        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM map_task_grid WHERE initiative_id = %s",
                (initiative_id,),
            )
            return [self._row_to_grid(row) for row in cur.fetchall()]

    def list_by_status(self, status: str) -> list[TaskGrid]:
        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM map_task_grid WHERE status = %s",
                (status,),
            )
            return [self._row_to_grid(row) for row in cur.fetchall()]

    def _row_to_grid(self, row: dict[str, Any]) -> TaskGrid:
        return TaskGrid(
            id=row["grid_id"],
            initiative_id=row["initiative_id"],
            geometry=row["geometry"],
            status=GridStatus(row["status"]),
            assigned_user_id=row.get("assigned_user_id"),
            locked_at=row.get("locked_at"),
            completed_at=row.get("completed_at"),
            review_notes=row.get("review_notes"),
        )

    def _row_to_polygon(self, row: dict[str, Any]) -> Polygon:
        return Polygon(
            id=row["id"],
            task_grid_id=row.get("task_grid_id"),
            polygon_set_id=row["polygon_set_id"],
            original_geometry=row["original_geometry"],
            qa_status=QaStatus(row["qa_status"]),
            confidence_avg=row.get("confidence_avg"),
            corrected_geometry=row.get("corrected_geometry"),
            properties=row.get("properties") or {},
        )


class PostgresUserRepository(AbstractUserRepository):
    def __init__(self, conn: psycopg2.extensions.connection) -> None:
        self.conn = conn
        self.seen: dict[UUID, User] = {}

    def add(self, user: User) -> None:
        self.seen[user.id] = user
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO users (id, email, name, role, credits_remaining)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (user.id, user.email, user.name, user.role, user.credits_remaining),
            )

    def get(self, user_id: UUID) -> User | None:
        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM users WHERE id = %s", (user_id,))
            row = cur.fetchone()
            if row is None:
                return None
            user = self._row_to_user(row)
            self.seen[user.id] = user
            return user

    def get_by_email(self, email: str) -> User | None:
        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM users WHERE email = %s", (email,))
            row = cur.fetchone()
            if row is None:
                return None
            return self._row_to_user(row)

    def _row_to_user(self, row: dict[str, Any]) -> User:
        return User(
            id=row["id"],
            email=row["email"],
            name=row["name"],
            role=row["role"],
            credits_remaining=Decimal(str(row["credits_remaining"])),
        )


class PostgresInitiativeRepository(AbstractInitiativeRepository):
    def __init__(self, conn: psycopg2.extensions.connection) -> None:
        self.conn = conn

    def add(self, initiative: Initiative) -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO initiatives (id, owner_id, name, region, status, grid_size_m, budget_credits)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    initiative.id, initiative.owner_id, initiative.name,
                    initiative.region, initiative.status.value,
                    initiative.grid_size_m, initiative.budget_credits,
                ),
            )

    def get(self, initiative_id: UUID) -> Initiative | None:
        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM initiatives WHERE id = %s", (initiative_id,))
            row = cur.fetchone()
            if row is None:
                return None
            return Initiative(
                id=row["id"],
                owner_id=row["owner_id"],
                name=row["name"],
                region=row["region"],
                status=InitiativeStatus(row["status"]),
                grid_size_m=row["grid_size_m"],
                budget_credits=row.get("budget_credits"),
                created_at=row.get("created_at"),
                completed_at=row.get("completed_at"),
            )


class PostgresCorrectionRepository(AbstractCorrectionRepository):
    def __init__(self, conn: psycopg2.extensions.connection) -> None:
        self.conn = conn

    def add(self, correction: Correction) -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO human_corrections (id, polygon_id, user_id, original_geometry,
                                               corrected_geometry, action, notes)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    correction.id, correction.polygon_id, correction.user_id,
                    correction.original_geometry, correction.corrected_geometry,
                    correction.action, correction.notes,
                ),
            )

    def get_by_polygon(self, polygon_id: UUID) -> list[Correction]:
        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM human_corrections WHERE polygon_id = %s ORDER BY created_at",
                (polygon_id,),
            )
            return [
                Correction(
                    id=row["id"],
                    polygon_id=row["polygon_id"],
                    user_id=row["user_id"],
                    original_geometry=row["original_geometry"],
                    corrected_geometry=row["corrected_geometry"],
                    action=row["action"],
                    notes=row.get("notes"),
                    created_at=row.get("created_at"),
                )
                for row in cur.fetchall()
            ]


class PostgresExportRepository(AbstractExportRepository):
    def __init__(self, conn: psycopg2.extensions.connection) -> None:
        self.conn = conn

    def add(self, job: ExportJob) -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO export_jobs (export_id, user_id, export_format, source_type,
                                         source_id, status, output_url, error_message)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    job.export_id, job.user_id, job.export_format,
                    job.source_type, job.source_id, job.status,
                    job.output_url, job.error_message,
                ),
            )

    def get(self, export_id: UUID) -> ExportJob | None:
        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM export_jobs WHERE export_id = %s", (export_id,))
            row = cur.fetchone()
            if row is None:
                return None
            return self._row_to_job(row)

    def list_by_user(self, user_id: UUID) -> list[ExportJob]:
        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM export_jobs WHERE user_id = %s ORDER BY created_at DESC",
                (user_id,),
            )
            return [self._row_to_job(row) for row in cur.fetchall()]

    def _row_to_job(self, row: dict) -> ExportJob:
        return ExportJob(
            export_id=row["export_id"],
            user_id=row["user_id"],
            export_format=row["export_format"],
            source_type=row["source_type"],
            source_id=row["source_id"],
            status=row["status"],
            output_url=row.get("output_url"),
            error_message=row.get("error_message"),
            created_at=row.get("created_at"),
            completed_at=row.get("completed_at"),
        )


class PostgresMarketplaceRepository(AbstractMarketplaceRepository):
    def __init__(self, conn: psycopg2.extensions.connection) -> None:
        self.conn = conn

    def add_listing(self, listing: MarketplaceListing) -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO marketplace_listings
                    (listing_id, seller_id, dataset_id, title, description,
                     price_tokens, geometry_count, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    listing.listing_id, listing.seller_id, listing.dataset_id,
                    listing.title, listing.description,
                    listing.price_tokens, listing.geometry_count, listing.status,
                ),
            )

    def get_listing(self, listing_id: UUID) -> MarketplaceListing | None:
        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM marketplace_listings WHERE listing_id = %s",
                (listing_id,),
            )
            row = cur.fetchone()
            if row is None:
                return None
            return self._row_to_listing(row)

    def list_active(self) -> list[MarketplaceListing]:
        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM marketplace_listings WHERE status = 'active' ORDER BY created_at DESC"
            )
            return [self._row_to_listing(row) for row in cur.fetchall()]

    def add_purchase(self, purchase: DatasetPurchase) -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO dataset_purchases
                    (purchase_id, listing_id, buyer_id, dataset_id, tokens_paid)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    purchase.purchase_id, purchase.listing_id, purchase.buyer_id,
                    purchase.dataset_id, purchase.tokens_paid,
                ),
            )

    def set_listing_status(self, listing_id: UUID, status: str) -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                "UPDATE marketplace_listings SET status = %s WHERE listing_id = %s",
                (status, listing_id),
            )

    def _row_to_listing(self, row: dict) -> MarketplaceListing:
        return MarketplaceListing(
            listing_id=row["listing_id"],
            seller_id=row["seller_id"],
            dataset_id=row["dataset_id"],
            title=row["title"],
            description=row.get("description"),
            price_tokens=row["price_tokens"],
            geometry_count=row["geometry_count"],
            status=row["status"],
            created_at=row.get("created_at"),
        )


class PostgresParticipantRepository(AbstractParticipantRepository):
    def __init__(self, conn: psycopg2.extensions.connection) -> None:
        self.conn = conn

    def add(self, participant: Participant) -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO initiative_participants (initiative_id, user_id, role)
                VALUES (%s, %s, %s)
                ON CONFLICT (initiative_id, user_id)
                DO UPDATE SET role = EXCLUDED.role
                """,
                (participant.initiative_id, participant.user_id, participant.role),
            )

    def list_by_initiative(self, initiative_id: UUID) -> list[Participant]:
        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM initiative_participants WHERE initiative_id = %s ORDER BY joined_at",
                (initiative_id,),
            )
            return [
                Participant(
                    initiative_id=row["initiative_id"],
                    user_id=row["user_id"],
                    role=row["role"],
                    joined_at=row.get("joined_at"),
                )
                for row in cur.fetchall()
            ]

    def list_by_user(self, user_id: UUID) -> list[Participant]:
        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM initiative_participants WHERE user_id = %s ORDER BY joined_at DESC",
                (user_id,),
            )
            return [
                Participant(
                    initiative_id=row["initiative_id"],
                    user_id=row["user_id"],
                    role=row["role"],
                    joined_at=row.get("joined_at"),
                )
                for row in cur.fetchall()
            ]


class FakeUserRepository(AbstractUserRepository):
    def __init__(self) -> None:
        self._users: dict[UUID, User] = {}

    def add(self, user: User) -> None:
        self._users[user.id] = user

    def get(self, user_id: UUID) -> User | None:
        return self._users.get(user_id)

    def get_by_email(self, email: str) -> User | None:
        for u in self._users.values():
            if u.email == email:
                return u
        return None


class FakeInitiativeRepository(AbstractInitiativeRepository):
    def __init__(self) -> None:
        self._initiatives: dict[UUID, Initiative] = {}

    def add(self, initiative: Initiative) -> None:
        self._initiatives[initiative.id] = initiative

    def get(self, initiative_id: UUID) -> Initiative | None:
        return self._initiatives.get(initiative_id)


class FakeCorrectionRepository(AbstractCorrectionRepository):
    def __init__(self) -> None:
        self._corrections: list[Correction] = []

    def add(self, correction: Correction) -> None:
        self._corrections.append(correction)

    def get_by_polygon(self, polygon_id: UUID) -> list[Correction]:
        return [c for c in self._corrections if c.polygon_id == polygon_id]


class FakeExportRepository(AbstractExportRepository):
    def __init__(self) -> None:
        self._jobs: dict[UUID, ExportJob] = {}

    def add(self, job: ExportJob) -> None:
        self._jobs[job.export_id] = job

    def get(self, export_id: UUID) -> ExportJob | None:
        return self._jobs.get(export_id)

    def list_by_user(self, user_id: UUID) -> list[ExportJob]:
        return [j for j in self._jobs.values() if j.user_id == user_id]


class FakeParticipantRepository(AbstractParticipantRepository):
    def __init__(self) -> None:
        self._participants: list[Participant] = []

    def add(self, participant: Participant) -> None:
        self._participants.append(participant)

    def list_by_initiative(self, initiative_id: UUID) -> list[Participant]:
        return [p for p in self._participants if p.initiative_id == initiative_id]

    def list_by_user(self, user_id: UUID) -> list[Participant]:
        return [p for p in self._participants if p.user_id == user_id]


class FakeMarketplaceRepository(AbstractMarketplaceRepository):
    def __init__(self) -> None:
        self._listings: dict[UUID, MarketplaceListing] = {}
        self._purchases: list[DatasetPurchase] = []

    def add_listing(self, listing: MarketplaceListing) -> None:
        self._listings[listing.listing_id] = listing

    def get_listing(self, listing_id: UUID) -> MarketplaceListing | None:
        return self._listings.get(listing_id)

    def list_active(self) -> list[MarketplaceListing]:
        return [l for l in self._listings.values() if l.status == "active"]

    def add_purchase(self, purchase: DatasetPurchase) -> None:
        self._purchases.append(purchase)

    def set_listing_status(self, listing_id: UUID, status: str) -> None:
        listing = self._listings.get(listing_id)
        if listing:
            listing.status = status
