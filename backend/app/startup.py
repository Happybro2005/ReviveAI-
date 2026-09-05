"""Background bootstrap for hosted deployments.

On a platform like Render the process must bind its port quickly or the deploy
is treated as failed. Seeding 40,000 sessions and training six models takes
several minutes on a 0.1-CPU instance, so running that *before* uvicorn starts
means nothing answers for the whole of it.

Instead the server binds immediately and the bootstrap runs on a background
thread. While it works:

  * /api/health reports `bootstrap` with the current stage, so the UI can say
    what is happening rather than looking broken,
  * endpoints that need a model return 503 with a clear message, which the
    frontend already renders as an error state rather than a blank page.

The heavy stages run as subprocesses, so their memory is released back to the
OS as each finishes instead of accumulating in the API process.

Enabled with RUN_BOOTSTRAP=1. Local development leaves it unset and keeps using
scripts/bootstrap.py directly.
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger("reviveai.bootstrap")

BACKEND_ROOT = Path(__file__).resolve().parents[1]

_state: dict[str, Any] = {
    "enabled": False,
    "stage": "not started",
    "done": False,
    "failed": False,
    "error": None,
    "started_at": None,
    "finished_at": None,
}
_lock = threading.Lock()


def status() -> dict[str, Any]:
    with _lock:
        s = dict(_state)
    if s["started_at"] and not s["finished_at"]:
        s["elapsed_seconds"] = round(time.time() - s["started_at"], 1)
    elif s["started_at"] and s["finished_at"]:
        s["elapsed_seconds"] = round(s["finished_at"] - s["started_at"], 1)
    return s


def _set(**kwargs: Any) -> None:
    with _lock:
        _state.update(kwargs)


def _run(cmd: list[str], stage: str) -> bool:
    _set(stage=stage)
    logger.info("bootstrap: %s", stage)
    t0 = time.time()
    try:
        result = subprocess.run(cmd, cwd=BACKEND_ROOT, capture_output=True, text=True)
    except Exception as exc:
        logger.exception("bootstrap: %s crashed", stage)
        _set(failed=True, error=f"{stage}: {exc}")
        return False
    if result.returncode != 0:
        tail = (result.stderr or result.stdout or "").strip().splitlines()[-5:]
        logger.error("bootstrap: %s failed (exit %s)\n%s",
                     stage, result.returncode, "\n".join(tail))
        _set(failed=True, error=f"{stage} failed: {' | '.join(tail)[:400]}")
        return False
    logger.info("bootstrap: %s done in %.1fs", stage, time.time() - t0)
    return True


def _bootstrap() -> None:
    """Runs on a background thread. Never raises into the server."""
    from sqlalchemy import text

    from .config import get_settings
    from .db import get_engine

    settings = get_settings()
    sessions = os.environ.get("BOOTSTRAP_SESSIONS", "40000")
    force = os.environ.get("FORCE_BOOTSTRAP", "").lower() in ("1", "true", "yes")
    _set(started_at=time.time())

    def count(table: str) -> int:
        try:
            with get_engine().connect() as conn:
                return int(conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one())
        except Exception:
            return -1

    # ---- wait for the database
    _set(stage="waiting for database")
    attempts = int(os.environ.get("DB_WAIT_ATTEMPTS", "60"))
    for attempt in range(1, attempts + 1):
        try:
            with get_engine().connect() as conn:
                conn.execute(text("SELECT 1"))
            logger.info("bootstrap: database reachable (attempt %d)", attempt)
            break
        except Exception as exc:
            msg = str(exc)
            if "could not translate host name" in msg or "Name or service not known" in msg:
                _set(failed=True, error=(
                    "The database hostname does not resolve. The service and the "
                    "database are almost certainly in DIFFERENT REGIONS - set the "
                    "same `region:` on both in render.yaml."))
                logger.error("bootstrap: database hostname does not resolve (region mismatch)")
                return
            if attempt == attempts:
                _set(failed=True, error=f"database unreachable after {attempts} attempts")
                return
            time.sleep(5)

    if not _run([sys.executable, "-m", "alembic", "upgrade", "head"], "migrations"):
        return

    if force or count("checkout_sessions") <= 0:
        cmd = [sys.executable, "scripts/generate_data.py", "--reset", "--sessions", sessions]
        if not _run(cmd, f"generating {int(sessions):,} sessions"):
            return
    else:
        logger.info("bootstrap: seed data present - skipped")

    if force or count("review_analysis") <= 0:
        cmd = [sys.executable, "scripts/analyze_reviews.py"]
        if force:
            cmd.append("--reset")
        if not _run(cmd, "analysing reviews"):
            return
    else:
        logger.info("bootstrap: reviews analysed - skipped")

    required = ["abandonment", "recovery", "return_risk", "rto_risk", "anomaly", "sentiment_clf"]
    missing = [m for m in required if not (settings.artifact_path / f"{m}.joblib").exists()]
    if force or missing:
        if not _run([sys.executable, "scripts/train_models.py", "--skip-importance"],
                    "training models"):
            return
        # Drop cached "model not found" state so the new artifacts are picked up.
        try:
            from .deps import get_store

            get_store().clear()
        except Exception:
            pass
    else:
        logger.info("bootstrap: models present - skipped")

    _set(stage="ready", done=True, finished_at=time.time())
    logger.info("bootstrap: ready")


def start_background_bootstrap() -> None:
    """Kick off the bootstrap thread if RUN_BOOTSTRAP is set."""
    if os.environ.get("RUN_BOOTSTRAP", "").lower() not in ("1", "true", "yes"):
        return
    _set(enabled=True, stage="starting")
    thread = threading.Thread(target=_bootstrap, name="bootstrap", daemon=True)
    thread.start()
    logger.info("bootstrap: started in background; the API is already serving")
