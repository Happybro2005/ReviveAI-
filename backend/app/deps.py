"""Shared FastAPI dependencies.

The model store is a process-wide singleton: artifacts load lazily on first use
and stay cached for the life of the process. Models are never trained here.
"""
from __future__ import annotations

from functools import lru_cache

from ml.common import ModelStore
from ml.decision.economics import CostModel

from .config import get_settings


@lru_cache(maxsize=1)
def get_store() -> ModelStore:
    return ModelStore(get_settings().artifact_path)


@lru_cache(maxsize=1)
def get_costs() -> CostModel:
    s = get_settings()
    return CostModel(
        email=s.email_cost,
        sms=s.sms_cost,
        whatsapp=s.whatsapp_cost,
        call=s.call_cost,
        manual_review=s.manual_review_cost,
        gross_margin=s.gross_margin,
    )


REQUIRED_MODELS = [
    "abandonment", "recovery", "return_risk", "rto_risk", "anomaly", "sentiment_clf"
]
