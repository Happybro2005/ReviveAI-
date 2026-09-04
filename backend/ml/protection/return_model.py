"""Return risk prediction.

Review-derived product signals (`voc_*`) are real input features here: a product
whose reviews are full of size complaints genuinely does get returned more, so
Voice of Customer feeds Revenue Protection through the model itself rather than
through a side panel.
"""
from __future__ import annotations

from typing import Any

from ..common import ModelStore, risk_level
from ..explainability.explainer import explain_row
from ..pipeline_builder import frame_for

MODEL_NAME = "return_risk"

# Which protection action addresses which dominant driver.
_ACTION_FOR_DRIVER = {
    "voc_size_fit_rate": "SIZE_RECOMMENDATION",
    "has_size_variants": "SIZE_RECOMMENDATION",
    "voc_quality_rate": "MANUAL_REVIEW",
    "voc_packaging_rate": "PACKAGING_REVIEW",
    "voc_delivery_rate": "DELIVERY_ESCALATION",
    "prior_return_rate": "MANUAL_REVIEW",
    "prior_return_count": "MANUAL_REVIEW",
}


def enrich(payload: dict[str, Any]) -> dict[str, Any]:
    data = dict(payload)
    orders = float(data.get("prior_order_count") or 0)
    returns = float(data.get("prior_return_count") or 0)
    if data.get("prior_return_rate") in (None, ""):
        data["prior_return_rate"] = (returns / orders) if orders > 0 else 0.0
    for flag in ("has_size_variants", "is_cod"):
        data[flag] = int(bool(data.get(flag)))
    for key in (
        "voc_review_count", "voc_avg_rating", "voc_size_fit_rate",
        "voc_quality_rate", "voc_delivery_rate", "voc_packaging_rate",
        "prior_rto_count", "quantity", "weight_kg",
    ):
        if data.get(key) in (None, ""):
            data[key] = 0.0
    if not data.get("quantity"):
        data["quantity"] = 1
    return data


def recommend_action(contributions: list[dict[str, Any]], level: str) -> str:
    """Pick the protection action that addresses the top *increasing* driver."""
    if level == "LOW":
        return "NO_ACTION"
    for c in contributions:
        if c["direction"] != "INCREASES":
            continue
        action = _ACTION_FOR_DRIVER.get(c["feature"])
        if action:
            return action
    return "MANUAL_REVIEW" if level == "HIGH" else "NO_ACTION"


def predict(
    payload: dict[str, Any],
    store: ModelStore,
    explain: bool = True,
    top_n: int = 6,
) -> dict[str, Any]:
    pipeline, meta = store.require(MODEL_NAME)
    row = frame_for(meta.feature_names, enrich(payload))
    probability = float(pipeline.predict_proba(row)[0][1])
    level = risk_level(probability)

    contributions = [
        c.to_dict()
        for c in explain_row(pipeline, row, meta.feature_names, top_n=top_n)
    ] if explain else []

    return {
        "return_probability": round(probability, 4),
        "risk_level": level,
        "top_factors": contributions,
        "recommended_action": recommend_action(contributions, level),
        "model_version": meta.version,
        "model_algorithm": meta.algorithm,
    }
