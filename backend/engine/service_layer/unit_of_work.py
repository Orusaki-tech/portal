from __future__ import annotations

from typing import Any, Protocol

import psycopg2

from backend.engine.adapters.repository import (
    AbstractCorrectionRepository,
    AbstractCreditTransactionRepository,
    AbstractExportRepository,
    AbstractInitiativeRepository,
    AbstractLeaderboardRepository,
    AbstractMarketplaceRepository,
    AbstractMlPolygonSetRepository,
    AbstractParticipantRepository,
    AbstractTaskGridRepository,
    AbstractUserRepository,
    AbstractValidationRunRepository,
    PostgresCorrectionRepository,
    PostgresCreditTransactionRepository,
    PostgresExportRepository,
    PostgresInitiativeRepository,
    PostgresLeaderboardRepository,
    PostgresMarketplaceRepository,
    PostgresMlPolygonSetRepository,
    PostgresParticipantRepository,
    PostgresTaskGridRepository,
    PostgresUserRepository,
    PostgresValidationRunRepository,
)


class UnitOfWork(Protocol):
    grid_repo: AbstractTaskGridRepository
    user_repo: AbstractUserRepository
    initiative_repo: AbstractInitiativeRepository
    correction_repo: AbstractCorrectionRepository
    export_repo: AbstractExportRepository
    participant_repo: AbstractParticipantRepository
    marketplace_repo: AbstractMarketplaceRepository
    polygon_set_repo: AbstractMlPolygonSetRepository
    leaderboard_repo: AbstractLeaderboardRepository
    credit_txn_repo: AbstractCreditTransactionRepository
    validation_run_repo: AbstractValidationRunRepository

    def __enter__(self) -> UnitOfWork: ...
    def __exit__(self, *args: Any) -> None: ...
    def commit(self) -> None: ...
    def rollback(self) -> None: ...
    def collect_events(self) -> list: ...


class FakeUnitOfWork:
    def __init__(
        self,
        grid_repo: AbstractTaskGridRepository | None = None,
        user_repo: AbstractUserRepository | None = None,
        initiative_repo: AbstractInitiativeRepository | None = None,
        correction_repo: AbstractCorrectionRepository | None = None,
        export_repo: AbstractExportRepository | None = None,
        participant_repo: AbstractParticipantRepository | None = None,
        marketplace_repo: AbstractMarketplaceRepository | None = None,
        polygon_set_repo: AbstractMlPolygonSetRepository | None = None,
        leaderboard_repo: AbstractLeaderboardRepository | None = None,
        credit_txn_repo: AbstractCreditTransactionRepository | None = None,
        validation_run_repo: AbstractValidationRunRepository | None = None,
    ) -> None:
        from backend.engine.adapters.repository import (
            FakeCorrectionRepository,
            FakeCreditTransactionRepository,
            FakeExportRepository,
            FakeInitiativeRepository,
            FakeLeaderboardRepository,
            FakeMarketplaceRepository,
            FakeMlPolygonSetRepository,
            FakeParticipantRepository,
            FakeTaskGridRepository,
            FakeUserRepository,
            FakeValidationRunRepository,
        )

        self.grid_repo = grid_repo or FakeTaskGridRepository()
        self.user_repo = user_repo or FakeUserRepository()
        self.initiative_repo = initiative_repo or FakeInitiativeRepository()
        self.correction_repo = correction_repo or FakeCorrectionRepository()
        self.export_repo = export_repo or FakeExportRepository()
        self.participant_repo = participant_repo or FakeParticipantRepository()
        self.marketplace_repo = marketplace_repo or FakeMarketplaceRepository()
        self.polygon_set_repo = polygon_set_repo or FakeMlPolygonSetRepository()
        self.leaderboard_repo = leaderboard_repo or FakeLeaderboardRepository()
        self.credit_txn_repo = credit_txn_repo or FakeCreditTransactionRepository()
        self.validation_run_repo = validation_run_repo or FakeValidationRunRepository()
        self.committed = False
        self.rolled_back = False
        self._events: list = []

    def __enter__(self) -> FakeUnitOfWork:
        return self

    def __exit__(self, *args: Any) -> None:
        pass

    def commit(self) -> None:
        self.committed = True
        self._events = self.collect_events()

    def rollback(self) -> None:
        self.rolled_back = True

    def collect_events(self) -> list:
        events = []
        for grid in self.grid_repo._grids.values():
            events.extend(grid.events)
            grid.clear_events()
        for user in self.user_repo._users.values():
            events.extend(user.events)
            user.clear_events()
        for entry in self.leaderboard_repo._entries.values():
            events.extend(entry.events)
            entry.clear_events()
        return events

    @property
    def events(self) -> list:
        return self._events


class PostgresUnitOfWork:
    def __init__(self, connection_factory: Any) -> None:
        self._conn_factory = connection_factory
        self.conn: psycopg2.extensions.connection | None = None
        self.grid_repo: PostgresTaskGridRepository | None = None
        self.user_repo: PostgresUserRepository | None = None
        self.initiative_repo: PostgresInitiativeRepository | None = None
        self.correction_repo: PostgresCorrectionRepository | None = None
        self.export_repo: PostgresExportRepository | None = None
        self.participant_repo: PostgresParticipantRepository | None = None
        self.marketplace_repo: PostgresMarketplaceRepository | None = None
        self.polygon_set_repo: PostgresMlPolygonSetRepository | None = None
        self.leaderboard_repo: PostgresLeaderboardRepository | None = None
        self.credit_txn_repo: PostgresCreditTransactionRepository | None = None
        self.validation_run_repo: PostgresValidationRunRepository | None = None
        self._events: list = []

    def __enter__(self) -> PostgresUnitOfWork:
        self.conn = self._conn_factory()
        self.conn.autocommit = False
        self.grid_repo = PostgresTaskGridRepository(self.conn)
        self.user_repo = PostgresUserRepository(self.conn)
        self.initiative_repo = PostgresInitiativeRepository(self.conn)
        self.correction_repo = PostgresCorrectionRepository(self.conn)
        self.export_repo = PostgresExportRepository(self.conn)
        self.participant_repo = PostgresParticipantRepository(self.conn)
        self.marketplace_repo = PostgresMarketplaceRepository(self.conn)
        self.polygon_set_repo = PostgresMlPolygonSetRepository(self.conn)
        self.leaderboard_repo = PostgresLeaderboardRepository(self.conn)
        self.credit_txn_repo = PostgresCreditTransactionRepository(self.conn)
        self.validation_run_repo = PostgresValidationRunRepository(self.conn)
        return self

    def __exit__(self, *args: Any) -> None:
        if self.conn:
            if args[0] is not None:
                self.conn.rollback()
            self.conn.close()

    def commit(self) -> None:
        if self.conn:
            self.conn.commit()
            self._events = self.collect_events()

    def rollback(self) -> None:
        if self.conn:
            self.conn.rollback()

    def collect_events(self) -> list:
        events: list = []
        if self.grid_repo:
            for grid in self.grid_repo.seen.values():
                events.extend(grid.events)
                grid.clear_events()
        if self.user_repo:
            for user in self.user_repo.seen.values():
                events.extend(user.events)
                user.clear_events()
        if self.leaderboard_repo:
            for entry in self.leaderboard_repo.seen.values():
                events.extend(entry.events)
                entry.clear_events()
        return events

    @property
    def events(self) -> list:
        return self._events
