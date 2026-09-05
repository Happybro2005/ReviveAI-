"""Health and model status endpoints."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..config import SYNTHETIC_DATA_DISCLOSURE
from ..db import check_connection, get_db
from ..deps import REQUIRED_MODELS, get_store
from ..startup import status as bootstrap_status
from ..schemas import HealthResponse

router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    ok, detail = check_connection()
    store = get_store()
    trained = [m for m in REQUIRED_MODELS if store.available(m)]
    missing = [m for m in REQUIRED_MODELS if not store.available(m)]

    reviews_analysed: bool | None = None
    if ok:
        try:
            from ..db import get_engine

            with get_engine().connect() as conn:
                n = conn.execute(text("SELECT COUNT(*) FROM review_analysis")).scalar()
            reviews_analysed = bool(n)
        except Exception:
            reviews_analysed = None

    # While a hosted deployment is still seeding, "degraded" is the honest
    # answer -- the service is up but not yet able to answer every endpoint.
    boot = bootstrap_status()
    if boot.get("enabled") and not boot.get("done"):
        overall = "starting" if not boot.get("failed") else "degraded"
    else:
        overall = "ok" if ok and not missing else "degraded"

    return HealthResponse(
        status=overall,
        database="connected" if ok else "unavailable",
        database_detail=detail if not ok else detail.split(",")[0],
        models_trained=trained,
        models_missing=missing,
        reviews_analysed=reviews_analysed,
        bootstrap=boot if boot.get("enabled") else None,
        disclosure=SYNTHETIC_DATA_DISCLOSURE,
    )


@router.get("/models/status")
def models_status() -> dict[str, Any]:
    store = get_store()
    return {
        "artifact_dir": str(store.artifact_dir),
        "models": [
            {
                "name": m,
                "trained": store.available(m),
                "path": str(store.artifact_dir / f"{m}.joblib"),
            }
            for m in REQUIRED_MODELS
        ],
        "disclosure": SYNTHETIC_DATA_DISCLOSURE,
    }


@router.get("/models/metrics")
def models_metrics(db: Session = Depends(get_db)) -> dict[str, Any]:
    """Evaluation metrics for every trained model, newest version per model."""
    store = get_store()
    artifacts = {a.get("name"): a for a in store.status()}

    registry_rows = db.execute(text("""
        SELECT DISTINCT ON (name) name, version, algorithm, trained_at,
               training_rows, notes
        FROM model_registry
        ORDER BY name, trained_at DESC
    """)).mappings().all()
    registry = {r["name"]: dict(r) for r in registry_rows}

    models = []
    for name in REQUIRED_MODELS:
        art = artifacts.get(name)
        reg = registry.get(name, {})
        models.append({
            "name": name,
            "trained": art is not None,
            "version": (art or {}).get("version") or reg.get("version"),
            "algorithm": (art or {}).get("algorithm") or reg.get("algorithm"),
            "trained_at": (art or {}).get("trained_at")
            or (reg.get("trained_at").isoformat() if reg.get("trained_at") else None),
            "training_rows": (art or {}).get("training_rows") or reg.get("training_rows"),
            "feature_names": (art or {}).get("feature_names", []),
            "metrics": (art or {}).get("metrics", {}),
            "notes": (art or {}).get("notes") or reg.get("notes"),
        })

    return {
        "models": models,
        "disclosure": SYNTHETIC_DATA_DISCLOSURE,
        "evaluation_note": (
            "All models are evaluated on a held-out later time period from the "
            "synthetic dataset. The NLP sentiment classifier is supervised by "
            "star ratings; aspect extraction and suggestion detection are "
            "rule-based and report no accuracy figure because no labelled "
            "aspect ground truth exists."
        ),
    }
