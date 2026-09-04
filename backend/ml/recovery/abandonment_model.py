"""Checkout abandonment prediction."""
from __future__ import annotations

from typing import Any

from ..common import ModelStore, risk_level
from ..explainability.explainer import explain_row
from ..pipeline_builder import frame_for

MODEL_NAME = "abandonment"


def enrich(payload: dict[str, Any]) -> dict[str, Any]:
    """Derive features the caller may not have supplied directly."""
    data = dict(payload)
    cart = float(data.get("cart_value") or 0.0)
    shipping = float(data.get("shipping_cost") or 0.0)
    if data.get("shipping_cart_ratio") in (None, ""):
        data["shipping_cart_ratio"] = (shipping / cart) if cart > 0 else 0.0
    for flag in ("payment_failed", "coupon_applied", "coupon_failed", "is_weekend"):
        data[flag] = int(bool(data.get(flag)))
    for key, default in (
        ("item_count", 1), ("payment_attempts", 0), ("session_duration_sec", 0),
        ("address_edits", 0), ("page_errors", 0), ("hour_of_day", 12),
        ("prior_order_count", 0), ("prior_abandonment_count", 0),
        ("prior_return_count", 0), ("prior_rto_count", 0),
    ):
        if data.get(key) in (None, ""):
            data[key] = default
    return data


def predict(
    payload: dict[str, Any],
    store: ModelStore,
    explain: bool = True,
    top_n: int = 6,
) -> dict[str, Any]:
    pipeline, meta = store.require(MODEL_NAME)
    data = enrich(payload)
    row = frame_for(meta.feature_names, data)
    probability = float(pipeline.predict_proba(row)[0][1])

    result: dict[str, Any] = {
        "abandonment_probability": round(probability, 4),
        "risk_level": risk_level(probability),
        "model_version": meta.version,
        "model_algorithm": meta.algorithm,
    }
    if explain:
        contributions = explain_row(pipeline, row, meta.feature_names, top_n=top_n)
        result["explanation"] = [c.to_dict() for c in contributions]
    return result
