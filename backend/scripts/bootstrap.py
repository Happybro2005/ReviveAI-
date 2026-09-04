"""One-shot deployment bootstrap: migrate, seed and train — but only if needed.

    python scripts/bootstrap.py

Runs before the API starts on a hosted deployment. It is **idempotent**: on a
cold start where the database is already populated it exits in well under a
second, so it can safely sit in the start command of a service that sleeps and
wakes repeatedly.

Each stage is skipped when its work is already done:

    migrations  -> skipped if alembic is already at head
    seed data   -> skipped if checkout_sessions has rows
    review NLP  -> skipped if review_analysis has rows
    training    -> skipped if all six model artifacts exist

Set BOOTSTRAP_SESSIONS to control dataset size (default 20000, which produces
roughly 50 MB — comfortably inside a free Postgres tier). Set FORCE_BOOTSTRAP=1
to rebuild everything from scratch.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import text  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.db import get_engine  # noqa: E402

REQUIRED_MODELS = [
    "abandonment", "recovery", "return_risk", "rto_risk", "anomaly", "sentiment_clf",
]


def log(msg: str) -> None:
    print(f"[bootstrap] {msg}", flush=True)


def run(cmd: list[str], label: str) -> bool:
    log(f"{label} ...")
    t0 = time.time()
    result = subprocess.run(cmd, cwd=BACKEND_ROOT)
    if result.returncode != 0:
        log(f"{label} FAILED (exit {result.returncode})")
        return False
    log(f"{label} done in {time.time() - t0:.1f}s")
    return True


def table_count(table: str) -> int:
    """Row count, or -1 if the table does not exist yet."""
    try:
        with get_engine().connect() as conn:
            return int(conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one())
    except Exception:
        return -1


def main() -> int:
    settings = get_settings()
    force = os.environ.get("FORCE_BOOTSTRAP", "").lower() in ("1", "true", "yes")
    sessions = int(os.environ.get("BOOTSTRAP_SESSIONS", "20000"))

    if not settings.database_url:
        log("ERROR: DATABASE_URL is not set.")
        return 1

    log(f"starting (sessions={sessions:,}, force={force})")

    # ---- wait for the database, which may still be provisioning on a first deploy
    attempts = int(os.environ.get("DB_WAIT_ATTEMPTS", "60"))
    for attempt in range(1, attempts + 1):
        try:
            with get_engine().connect() as conn:
                conn.execute(text("SELECT 1"))
            log(f"database reachable (attempt {attempt})")
            break
        except Exception as exc:
            message = str(exc)
            # A name-resolution failure is not a transient startup delay: the
            # internal hostname only resolves inside the database's own region,
            # so retrying for five minutes just hides a configuration error.
            if "could not translate host name" in message or "Name or service not known" in message:
                log("ERROR: the database hostname does not resolve.")
                log("  The service and the database are almost certainly in")
                log("  DIFFERENT REGIONS. Render's internal hostname only resolves")
                log("  within one region. Set the same `region:` on both the")
                log("  database and the web service in render.yaml.")
                log(f"  original error: {message.splitlines()[0]}")
                return 1
            if attempt == attempts:
                log(f"ERROR: database unreachable after {attempts} attempts: {exc}")
                return 1
            if attempt % 10 == 0:
                log(f"  still waiting for the database ({attempt}/{attempts}) ...")
            time.sleep(5)

    # ---- 1. migrations (alembic is itself idempotent)
    if not run([sys.executable, "-m", "alembic", "upgrade", "head"], "migrations"):
        return 1

    # ---- 2. synthetic data
    n_sessions = table_count("checkout_sessions")
    if force or n_sessions <= 0:
        cmd = [sys.executable, "scripts/generate_data.py", "--reset",
               "--sessions", str(sessions)]
        if not run(cmd, f"generating {sessions:,} sessions"):
            return 1
    else:
        log(f"seed data present ({n_sessions:,} sessions) - skipped")

    # ---- 3. review analysis (must precede training)
    n_analysed = table_count("review_analysis")
    if force or n_analysed <= 0:
        cmd = [sys.executable, "scripts/analyze_reviews.py"]
        if force:
            cmd.append("--reset")
        if not run(cmd, "analysing reviews"):
            return 1
    else:
        log(f"reviews analysed ({n_analysed:,}) - skipped")

    # ---- 4. model training
    artifact_dir = settings.artifact_path
    missing = [m for m in REQUIRED_MODELS if not (artifact_dir / f"{m}.joblib").exists()]
    if force or missing:
        if missing:
            log(f"missing models: {', '.join(missing)}")
        # Permutation importance is the slow part of training and is only used
        # by the Model Insights charts, so it is skipped on a memory-limited host.
        if not run([sys.executable, "scripts/train_models.py", "--skip-importance"],
                   "training models"):
            return 1
    else:
        log("all six models present - skipped")

    log("ready")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
