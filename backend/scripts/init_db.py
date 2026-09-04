"""Create the ReviveAI database if it does not exist, then report status.

Usage:
    python scripts/init_db.py

Reads ADMIN_DATABASE_URL (a connection to the server's default `postgres`
database) and DATABASE_URL (the ReviveAI database) from .env. Creating the
database is separate from migrating it -- run `alembic upgrade head` after this.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402
from sqlalchemy.exc import SQLAlchemyError  # noqa: E402

from app.config import get_settings  # noqa: E402


def main() -> int:
    settings = get_settings()
    if not settings.database_url or "CHANGE_ME" in settings.database_url:
        print("ERROR: DATABASE_URL is unset or still contains CHANGE_ME.")
        print("Copy .env.example to .env and fill in your PostgreSQL password.")
        return 1

    target_url = make_url(settings.database_url)
    db_name = target_url.database
    admin_url = settings.admin_database_url or str(target_url.set(database="postgres"))

    try:
        admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT", future=True)
        with admin_engine.connect() as conn:
            exists = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": db_name}
            ).scalar()
            if exists:
                print(f"Database '{db_name}' already exists.")
            else:
                # db_name comes from our own parsed URL, not user input at runtime.
                conn.execute(text(f'CREATE DATABASE "{db_name}"'))
                print(f"Created database '{db_name}'.")
    except SQLAlchemyError as exc:
        print(f"ERROR connecting with ADMIN_DATABASE_URL: {exc}")
        return 1

    try:
        engine = create_engine(settings.database_url, future=True)
        with engine.connect() as conn:
            version = conn.execute(text("SELECT version()")).scalar_one()
        print(f"Connected to '{db_name}'.")
        print(f"Server: {str(version).split(',')[0]}")
    except SQLAlchemyError as exc:
        print(f"ERROR connecting to target database: {exc}")
        return 1

    print("\nNext: cd backend && alembic upgrade head")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
