"""Target-leakage guard.

Rule 3 of the project brief: no future/outcome information may ever be used as
an input feature. This module is the single place that defines what "outcome"
means for each model, and it is enforced in two places:

  * `assert_no_leakage()` runs inside every training routine, so a leaky feature
    set raises before a model is ever written to disk.
  * `tests/test_leakage.py` asserts the same rules independently.

Forbidden names are matched case-insensitively against both the exact feature
name and its substrings, because engineered features tend to inherit the name of
the column they came from (e.g. `recovered_revenue_log`).
"""
from __future__ import annotations


class LeakageError(AssertionError):
    """Raised when a feature set contains outcome information."""


# Columns that describe what happened *after* the event being predicted.
# Shared across all models: none of these may appear in any feature set.
GLOBAL_FORBIDDEN: set[str] = {
    "recovered",
    "recovered_at",
    "recovered_revenue",
    "converted",
    "converted_at",
    "conversion",
    "conversion_id",
    "realised_profit",
    "realised_cost",
    "outcome",
    "intervention_result",
    "recovery_channel",
    "expected_profit",
}

# Per-model additions. The key is the model name used in the registry.
MODEL_FORBIDDEN: dict[str, set[str]] = {
    "abandonment": {
        # The target itself, and anything only knowable once it is decided.
        "abandoned",
        "abandoned_at",
        "abandoned_cart_id",
        "primary_reason",
        "reason_confidence",
        "order_id",
        "order_ref",
        "order_value",
        "order_status",
        # Post-abandonment treatment
        "action",
        "channel",
        "intervention_cost",
        "discount_cost",
        "sent_at",
        "predicted_probability",
    },
    "recovery": {
        # `recovered` is the target. The action taken IS a legitimate input here
        # (the model answers "will this action recover this cart?"), so `action`
        # is deliberately absent from this set.
        "recovered",
        "recovered_at",
        "recovered_revenue",
    },
    "return_risk": {
        "returned",
        "return_reason",
        "refund_amount",
        "return_status",
        "requested_at",
        "return_ref",
    },
    "rto_risk": {
        "is_rto",
        "rto_reason",
        "delivered_at",
        "actual_days",
        "delivery_attempts",  # only known after delivery is attempted
        "status",
        "measured_weight_kg",
    },
}


def forbidden_for(model: str) -> set[str]:
    return GLOBAL_FORBIDDEN | MODEL_FORBIDDEN.get(model, set())


def assert_no_leakage(feature_names: list[str], model: str) -> None:
    """Raise LeakageError if any feature encodes an outcome for `model`."""
    forbidden = forbidden_for(model)
    offenders: list[str] = []
    for name in feature_names:
        low = name.lower()
        for bad in forbidden:
            if low == bad or bad in low:
                offenders.append(f"{name} (matches forbidden '{bad}')")
                break
    if offenders:
        raise LeakageError(
            f"Target leakage detected in '{model}' feature set:\n  - "
            + "\n  - ".join(offenders)
        )
