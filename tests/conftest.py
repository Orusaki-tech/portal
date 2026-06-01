from __future__ import annotations

from os import environ

import psycopg2
import pytest


def db_url_params() -> dict[str, str]:
    return {
        "host": environ.get("DB_HOST", "localhost"),
        "port": environ.get("DB_PORT", "5432"),
        "dbname": environ.get("DB_NAME", "realitysync"),
        "user": environ.get("DB_USER", "realitysync"),
        "password": environ.get("DB_PASSWORD", "realitysync"),
    }


@pytest.fixture(scope="session")
def db_conn() -> psycopg2.extensions.connection:
    conn = psycopg2.connect(**db_url_params())
    conn.autocommit = True
    return conn
