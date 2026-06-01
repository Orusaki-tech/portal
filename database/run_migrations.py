#!/usr/bin/env python3
"""Run database migrations in order, tracking applied migrations."""

import os
import re
from pathlib import Path

import dotenv
import psycopg2

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"
TRACKING_TABLE = "_migrations"


def get_connection():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "5432")),
        dbname=os.getenv("DB_NAME", "realitysync"),
        user=os.getenv("DB_USER", "realitysync"),
        password=os.getenv("DB_PASSWORD", "realitysync"),
    )


def ensure_tracking_table(conn):
    with conn.cursor() as cur:
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS {TRACKING_TABLE} (
                filename VARCHAR(255) PRIMARY KEY,
                applied_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
    conn.commit()


def get_applied(conn):
    with conn.cursor() as cur:
        cur.execute(f"SELECT filename FROM {TRACKING_TABLE} ORDER BY filename")
        return {row[0] for row in cur.fetchall()}


def mark_applied(conn, filename):
    with conn.cursor() as cur:
        cur.execute(
            f"INSERT INTO {TRACKING_TABLE} (filename) VALUES (%s)",
            (filename,),
        )
    conn.commit()


def get_migration_files():
    pattern = re.compile(r"^\d{3}_.+\.sql$")
    files = sorted(
        f for f in os.listdir(MIGRATIONS_DIR) if pattern.match(f)
    )
    return files


def run_migration(conn, filename):
    path = MIGRATIONS_DIR / filename
    sql = path.read_text()
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()
    mark_applied(conn, filename)
    print(f"  ✓ {filename}")


def main():
    dotenv.load_dotenv()

    print("Connecting to PostGIS...")
    conn = get_connection()
    ensure_tracking_table(conn)

    applied = get_applied(conn)
    pending = [f for f in get_migration_files() if f not in applied]

    if not pending:
        print("All migrations already applied.")
        conn.close()
        return

    print(f"Applying {len(pending)} migration(s):")
    for filename in pending:
        run_migration(conn, filename)

    print("Done.")
    conn.close()


if __name__ == "__main__":
    main()
