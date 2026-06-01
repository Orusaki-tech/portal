from __future__ import annotations

from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from backend.engine.domain.events import PolygonValidated
from backend.engine.domain.models import GridStatus, Polygon, TaskGrid, User
from backend.engine.service_layer.unit_of_work import PostgresUnitOfWork


class TestPostgresUnitOfWork:
    def test_can_add_grid_and_commit(self, pg_uow: PostgresUnitOfWork, seeded_initiative_id: UUID):
        grid = TaskGrid(id=uuid4(), initiative_id=seeded_initiative_id, geometry="POLYGON((0 0,1 0,1 1,0 1,0 0))")
        with pg_uow:
            pg_uow.grid_repo.add(grid)
            pg_uow.commit()

        with pg_uow as uow2:
            loaded = uow2.grid_repo.get(grid.id)
            assert loaded is not None
            assert loaded.id == grid.id
            assert loaded.status == GridStatus.PENDING
            assert loaded.geometry == grid.geometry

    def test_rollback_undoes_insert(self, pg_uow: PostgresUnitOfWork, seeded_initiative_id: UUID):
        grid = TaskGrid(id=uuid4(), initiative_id=seeded_initiative_id, geometry="POLYGON((0 0,1 0,1 1,0 1,0 0))")
        with pg_uow:
            pg_uow.grid_repo.add(grid)
            pg_uow.rollback()

        with pg_uow as uow2:
            loaded = uow2.grid_repo.get(grid.id)
            assert loaded is None

    def test_commit_without_explicit_rollback_persists(self, pg_uow: PostgresUnitOfWork, seeded_initiative_id: UUID):
        grid = TaskGrid(id=uuid4(), initiative_id=seeded_initiative_id, geometry="POLYGON((0 0,1 0,1 1,0 1,0 0))")
        with pg_uow:
            pg_uow.grid_repo.add(grid)
            pg_uow.commit()

        with pg_uow as uow2:
            assert uow2.grid_repo.get(grid.id) is not None

    def test_exception_causes_rollback(self, pg_uow: PostgresUnitOfWork, seeded_initiative_id: UUID):
        grid = TaskGrid(id=uuid4(), initiative_id=seeded_initiative_id, geometry="POLYGON((0 0,1 0,1 1,0 1,0 0))")
        with pytest.raises(RuntimeError):
            with pg_uow:
                pg_uow.grid_repo.add(grid)
                raise RuntimeError("boom")

        with pg_uow as uow2:
            loaded = uow2.grid_repo.get(grid.id)
            assert loaded is None

    def test_collects_events_from_seen_aggregates(
        self, pg_uow: PostgresUnitOfWork, seeded_initiative_id: UUID, seeded_polygon_set_id: UUID
    ):
        grid = TaskGrid(id=uuid4(), initiative_id=seeded_initiative_id, geometry="POLYGON((0 0,1 0,1 1,0 1,0 0))")
        polygon = Polygon(id=uuid4(), task_grid_id=grid.id, polygon_set_id=seeded_polygon_set_id, original_geometry="POLYGON((0 0,1 0,1 1,0 1,0 0))")
        grid.polygons.append(polygon)

        with pg_uow:
            pg_uow.grid_repo.add(grid)
            pg_uow.commit()

        with pg_uow as uow2:
            loaded = uow2.grid_repo.get(grid.id)
            assert loaded is not None
            loaded.raise_event(PolygonValidated(polygon_id=polygon.id, confidence=0.95, is_ambiguous=False))
            uow2.commit()
            assert len(uow2.events) == 1
            assert isinstance(uow2.events[0], PolygonValidated)

    def test_add_and_get_user(self, pg_uow: PostgresUnitOfWork):
        user = User(id=uuid4(), email="test@example.com", name="Test User", role="annotator", credits_remaining=Decimal("100"))
        with pg_uow:
            pg_uow.user_repo.add(user)
            pg_uow.commit()

        with pg_uow as uow2:
            loaded = uow2.user_repo.get(user.id)
            assert loaded is not None
            assert loaded.email == "test@example.com"
            assert loaded.credits_remaining == Decimal("100")

    def test_get_user_by_email(self, pg_uow: PostgresUnitOfWork):
        user = User(id=uuid4(), email="findme@example.com", name="Find Me", role="reviewer", credits_remaining=Decimal("50"))
        with pg_uow:
            pg_uow.user_repo.add(user)
            pg_uow.commit()

        with pg_uow as uow2:
            loaded = uow2.user_repo.get_by_email("findme@example.com")
            assert loaded is not None
            assert loaded.name == "Find Me"

    def test_get_by_initiative(
        self,
        pg_uow: PostgresUnitOfWork,
        seeded_initiative_id: UUID,
        seeded_user_id: UUID,
        db_conn,
        migrated_schema,
    ):
        initiative_id = seeded_initiative_id
        grid_a = TaskGrid(id=uuid4(), initiative_id=initiative_id, geometry="POLYGON((0 0,1 0,1 1,0 1,0 0))")
        grid_b = TaskGrid(id=uuid4(), initiative_id=initiative_id, geometry="POLYGON((2 2,3 2,3 3,2 3,2 2))")
        other_init_id = uuid4()
        with db_conn.cursor() as cur:
            cur.execute(f"SET search_path TO {migrated_schema}, public")
            cur.execute(
                "INSERT INTO initiatives (id, owner_id, name, region, status, budget_credits) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (other_init_id, seeded_user_id, "Other", "POLYGON((0 0,1 0,1 1,0 1,0 0))", "active", 500.00),
            )

        other = TaskGrid(id=uuid4(), initiative_id=other_init_id, geometry="POLYGON((4 4,5 4,5 5,4 5,4 4))")
        with pg_uow:
            for g in (grid_a, grid_b, other):
                pg_uow.grid_repo.add(g)
            pg_uow.commit()

        with pg_uow as uow2:
            grids = uow2.grid_repo.get_by_initiative(initiative_id)
            assert len(grids) == 2
            assert {g.id for g in grids} == {grid_a.id, grid_b.id}

    def test_list_by_status(self, pg_uow: PostgresUnitOfWork, seeded_initiative_id: UUID, seeded_user_id: UUID):
        locked = TaskGrid(id=uuid4(), initiative_id=seeded_initiative_id, geometry="POLYGON((0 0,1 0,1 1,0 1,0 0))")
        locked.lock(user_id=seeded_user_id)
        pending = TaskGrid(id=uuid4(), initiative_id=seeded_initiative_id, geometry="POLYGON((2 2,3 2,3 3,2 3,2 2))")

        with pg_uow:
            pg_uow.grid_repo.add(locked)
            pg_uow.grid_repo.add(pending)
            pg_uow.commit()

        with pg_uow as uow2:
            locked_list = uow2.grid_repo.list_by_status("in_progress")
            assert len(locked_list) == 1
            assert locked_list[0].id == locked.id

            pending_list = uow2.grid_repo.list_by_status("pending")
            assert len(pending_list) == 1
            assert pending_list[0].id == pending.id
