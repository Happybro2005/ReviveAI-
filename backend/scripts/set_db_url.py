"""Write DATABASE_URL / ADMIN_DATABASE_URL into .env, safely.

    python scripts/set_db_url.py

Prompts for the PostgreSQL password with hidden input, percent-encodes it so
special characters survive the URL, writes the two connection strings into .env,
and tests the connection.

The password is never printed, never logged, and never echoed to the terminal.
Only the masked form of the URL is displayed.
"""
from __future__ import annotations

import getpass
import sys
from pathlib import Path
from urllib.parse import quote

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = REPO_ROOT / ".env"
ENV_EXAMPLE = REPO_ROOT / ".env.example"

sys.path.insert(0, str(BACKEND_ROOT))


def upsert(lines: list[str], key: str, value: str) -> list[str]:
    """Replace KEY=... in place, or append it if absent."""
    out, replaced = [], False
    for line in lines:
        if line.strip().startswith(f"{key}=") and not line.strip().startswith("#"):
            out.append(f"{key}={value}")
            replaced = True
        else:
            out.append(line)
    if not replaced:
        out.append(f"{key}={value}")
    return out


def main() -> int:
    if not ENV_PATH.exists():
        if ENV_EXAMPLE.exists():
            ENV_PATH.write_text(ENV_EXAMPLE.read_text(encoding="utf-8"), encoding="utf-8")
            print(f"Created {ENV_PATH} from .env.example")
        else:
            ENV_PATH.write_text("", encoding="utf-8")

    print("PostgreSQL connection setup")
    print("  Nothing you type below is displayed or stored anywhere but .env.\n")

    host = input("  Host [localhost]: ").strip() or "localhost"
    port = input("  Port [5432]: ").strip() or "5432"
    user = input("  Username [postgres]: ").strip() or "postgres"
    dbname = input("  Database to create/use [reviveai]: ").strip() or "reviveai"

    password = getpass.getpass("  Password (hidden, press Enter when done): ")
    if not password:
        print("\nNo password entered. Nothing was written.")
        return 1

    if not port.isdigit():
        print(f"\nPort must be numeric, got {port!r}. Nothing was written.")
        return 1

    # Percent-encode so '@', ':', '/', '#', '?', '%' and spaces survive the URL.
    safe_user = quote(user, safe="")
    safe_password = quote(password, safe="")

    base = f"postgresql+psycopg2://{safe_user}:{safe_password}@{host}:{port}"
    database_url = f"{base}/{dbname}"
    admin_url = f"{base}/postgres"
    masked = f"postgresql+psycopg2://{safe_user}:****@{host}:{port}/{dbname}"

    if safe_password != password:
        print("\n  Note: your password contained characters that needed URL encoding.")
        print("  That has been handled automatically.")

    lines = ENV_PATH.read_text(encoding="utf-8").splitlines()
    lines = upsert(lines, "DATABASE_URL", database_url)
    lines = upsert(lines, "ADMIN_DATABASE_URL", admin_url)
    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"\nWrote to {ENV_PATH}")
    print(f"  DATABASE_URL = {masked}")

    # Verify against the maintenance database, which always exists.
    print("\nTesting connection...")
    try:
        from sqlalchemy import create_engine, text

        engine = create_engine(admin_url, future=True)
        with engine.connect() as conn:
            version = conn.execute(text("SELECT version()")).scalar_one()
            exists = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": dbname}
            ).scalar()
        print(f"  Connected: {str(version).split(',')[0]}")
        print(
            f"  Database '{dbname}': "
            + ("already exists" if exists else "not created yet")
        )
    except Exception as exc:
        message = str(exc)
        # Never echo the password back, even inside a driver error message.
        message = message.replace(password, "****").replace(safe_password, "****")
        print(f"  FAILED: {type(exc).__name__}")
        print(f"  {message[:300]}")
        print("\n  The password was still written to .env. Re-run this script to")
        print("  correct it, or check that the PostgreSQL service is running.")
        return 1

    print("\nNext:")
    print("  python scripts/init_db.py")
    print("  alembic upgrade head")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
