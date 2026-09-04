"""Recovery probability prediction.

This is a genuinely separate model from the abandonment model, trained on a
different population (abandoned carts only) against a different target
(`recovered`). It is not a transformation of the abandonment score.

`action` is an input feature, which is what lets the decision engine ask
"what is p(recovery) if I send a 10% discount?" versus "...if I do nothing?"
and take the difference as the uplift.
"""
from __future__ import annotations

from typing import Any

from ..common import ModelStore
from ..decision.economics import RECOVERY_ACTIONS
from ..explainability.explainer import explain_row
from ..pipeline_builder import frame_for

MODEL_NAME = "recovery"


def enrich(payload: dict[str, Any], action: str) -> dict[str, Any]:
    data = dict(payload)
    cart = float(data.get("cart_value") or 0.0)
    shipping = float(data.get("shipping_cost") or 0.0)
    if data.get("shipping_cart_ratio") in (None, ""):
        data["shipping_cart_ratio"] = (shipping / cart) if cart > 0 else 0.0
    for flag in ("payment_failed", "coupon_failed"):
        data[flag] = int(bool(data.get(flag)))
    for key, default in (
        ("item_count", 1), ("payment_attempts", 0), ("session_duration_sec", 0),
        ("page_errors", 0), ("prior_order_count", 0),
        ("prior_abandonment_count", 0), ("prior_return_count", 0),
    ):
        if data.get(key) in (None, ""):
            data[key] = default
    data["action"] = action
    return data


def predict(
    payload: dict[str, Any],
    action: str,
    store: ModelStore,
    explain: bool = False,
    top_n: int = 6,
) -> dict[str, Any]:
    pipeline, meta = store.require(MODEL_NAME)
    row = frame_for(meta.feature_names, enrich(payload, action))
    probability = float(pipeline.predict_proba(row)[0][1])
    out: dict[str, Any] = {
        "action": action,
        "recovery_probability": round(probability, 4),
        "model_version": meta.version,
    }
    if explain:
        out["explanation"] = [
            c.to_dict()
            for c in explain_row(pipeline, row, meta.feature_names, top_n=top_n)
        ]
    return out


def predict_all_actions(
    payload: dict[str, Any],
    store: ModelStore,
    actions: list[str] | None = None,
) -> dict[str, float]:
    """Score every candidate action in one pass -- the decision engine's input."""
    pipeline, meta = store.require(MODEL_NAME)
    actions = actions or RECOVERY_ACTIONS
    import pandas as pd

    rows = [enrich(payload, a) for a in actions]
    frame = pd.DataFrame(
        [{f: r.get(f, None) for f in meta.feature_names} for r in rows],
        columns=meta.feature_names,
    )
    probabilities = pipeline.predict_proba(frame)[:, 1]
    return {a: float(p) for a, p in zip(actions, probabilities)}
