"""RTO (return-to-origin) risk prediction.

Scored at order placement, using only what is knowable then. Nothing about how
the delivery actually went is available to this model -- that would be useless
in production, since the only moment an RTO can be prevented is before dispatch.

A high score never auto-rejects a customer. The recommended action is always a
confirmation or a review step; the decision is left with the seller.
"""
from __future__ import annotations

from typing import Any

from ..common import ModelStore, risk_level
from ..explainability.explainer import explain_row
from ..pipeline_builder import frame_for

MODEL_NAME = "rto_risk"

_ACTION_FOR_DRIVER = {
    "is_cod": "PAYMENT_CONFIRMATION",
    "prior_rto_count": "ORDER_CONFIRMATION",
    "prior_rto_rate": "ORDER_CONFIRMATION",
    "courier": "LOGISTICS_REVIEW",
    "city": "LOGISTICS_REVIEW",
    "promised_days": "DELIVERY_ESCALATION",
    "order_value": "ORDER_CONFIRMATION",
}


def enrich(payload: dict[str, Any]) -> dict[str, Any]:
    data = dict(payload)
    orders = float(data.get("prior_order_count") or 0)
    rto = float(data.get("prior_rto_count") or 0)
    if data.get("prior_rto_rate") in (None, ""):
        data["prior_rto_rate"] = (rto / orders) if orders > 0 else 0.0
    method = str(data.get("payment_method") or "").upper()
    if data.get("is_cod") in (None, ""):
        data["is_cod"] = 1 if method == "COD" else 0
    data["is_cod"] = int(bool(data["is_cod"]))
    for key, default in (
        ("quantity", 1), ("weight_kg", 0.5), ("promised_days", 4),
        ("prior_order_count", 0), ("prior_rto_count", 0), ("prior_return_count", 0),
    ):
        if data.get(key) in (None, ""):
            data[key] = default
    return data


def recommend_action(
    contributions: list[dict[str, Any]], level: str, is_cod: bool
) -> str:
    if level == "LOW":
        return "NO_ACTION"
    for c in contributions:
        if c["direction"] != "INCREASES":
            continue
        action = _ACTION_FOR_DRIVER.get(c["feature"])
        if action == "PAYMENT_CONFIRMATION" and not is_cod:
            continue  # already prepaid; nothing to convert
        if action:
            return action
    return "ORDER_CONFIRMATION"


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
    level = risk_level(probability)

    contributions = [
        c.to_dict()
        for c in explain_row(pipeline, row, meta.feature_names, top_n=top_n)
    ] if explain else []

    return {
        "rto_probability": round(probability, 4),
        "risk_level": level,
        "top_factors": contributions,
        "recommended_action": recommend_action(contributions, level, bool(data["is_cod"])),
        "model_version": meta.version,
        "model_algorithm": meta.algorithm,
        "policy_note": (
            "A high RTO score is a prompt to confirm the order, never an "
            "instruction to reject the customer."
        ),
    }
