from __future__ import annotations

import glob
from collections.abc import Generator
from uuid import UUID, uuid4

import psycopg2
import pytest

from backend.engine.service_layer.unit_of_work import PostgresUnitOfWork


def _apply_migrations(conn: psycopg2.extensions.connection, schema: str) -> None:
    migrations = sorted(glob.glob("database/migrations/[0-9]*.sql"))
    assert migrations, "No migration files found"
    with conn.cursor() as cur:
        cur.execute(f"SET search_path TO {schema}, public")
        for path in migrations:
            sql = open(path).read()
            cur.execute(sql)
    conn.commit()


@pytest.fixture(scope="function")
def migrated_schema(db_conn: psycopg2.extensions.connection) -> Generator[str, None, None]:
    schema = f"test_realitysync_{uuid4().hex[:8]}"
    with db_conn.cursor() as cur:
        cur.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
    _apply_migrations(db_conn, schema)
    try:
        yield schema
    finally:
        with db_conn.cursor() as cur:
            cur.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")


@pytest.fixture
def seeded_user_id(
    db_conn: psycopg2.extensions.connection,
    migrated_schema: str,
) -> UUID:
    uid = uuid4()
    with db_conn.cursor() as cur:
        cur.execute(f"SET search_path TO {migrated_schema}, public")
        cur.execute(
            "INSERT INTO users (id, email, name, role, credits_remaining) "
            "VALUES (%s, %s, %s, %s, %s)",
            (uid, f"{uid.hex[:8]}@test.com", "Seed User", "manager", 10000.00),
        )
    return uid


@pytest.fixture
def seeded_initiative_id(
    db_conn: psycopg2.extensions.connection,
    migrated_schema: str,
    seeded_user_id: UUID,
) -> UUID:
    init_id = uuid4()
    with db_conn.cursor() as cur:
        cur.execute(f"SET search_path TO {migrated_schema}, public")
        cur.execute(
            "INSERT INTO initiatives (id, owner_id, name, region, status, budget_credits) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (
                init_id,
                seeded_user_id,
                "Test Initiative",
                "POLYGON((0 0,1 0,1 1,0 1,0 0))",
                "active",
                1000.00,
            ),
        )
    return init_id


@pytest.fixture
def seeded_polygon_set_id(
    db_conn: psycopg2.extensions.connection,
    migrated_schema: str,
    seeded_user_id: UUID,
) -> UUID:
    ps_id = uuid4()
    with db_conn.cursor() as cur:
        cur.execute(f"SET search_path TO {migrated_schema}, public")
        cur.execute(
            "INSERT INTO ml_polygon_sets (id, user_id, name) "
            "VALUES (%s, %s, %s)",
            (ps_id, seeded_user_id, "Test Polygon Set"),
        )
    return ps_id


@pytest.fixture
def pg_uow(
    db_conn: psycopg2.extensions.connection,
    migrated_schema: str,
) -> Generator[PostgresUnitOfWork, None, None]:
    def _factory() -> psycopg2.extensions.connection:
        c = psycopg2.connect(
            host=db_conn.info.host,
            port=db_conn.info.port,
            dbname=db_conn.info.dbname,
            user=db_conn.info.user,
            password=db_conn.info.password,
        )
        c.autocommit = True
        with c.cursor() as cur:
            cur.execute(f"SET search_path TO {migrated_schema}, public")
        c.autocommit = False
        return c

    yield PostgresUnitOfWork(_factory)
