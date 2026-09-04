"""Explainability (XAI).

Local explanations use SHAP's TreeExplainer against the gradient-boosted model
inside each pipeline. Contributions are real per-feature SHAP values for the
specific row being scored -- nothing is hard-coded, and the same input always
produces the same explanation.

One-hot columns are folded back to their source feature so the UI shows
"Payment method" rather than "payment_method_UPI", with the raw value attached
as context. Global importance uses permutation importance on a held-out sample,
which is model-agnostic and does not assume feature independence the way split
counts do.
"""
from __future__ import annotations

import re
import threading
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from sklearn.pipeline import Pipeline

# Readable names for everything the UI can surface.
FEATURE_LABELS: dict[str, str] = {
    "cart_value": "Cart value",
    "item_count": "Items in cart",
    "shipping_cost": "Shipping cost",
    "shipping_cart_ratio": "Shipping as % of cart",
    "payment_attempts": "Payment attempts",
    "payment_failed": "Payment failure",
    "session_duration_sec": "Time spent in checkout",
    "address_edits": "Address edits",
    "page_errors": "Page errors",
    "hour_of_day": "Hour of day",
    "is_weekend": "Weekend session",
    "coupon_applied": "Coupon applied",
    "coupon_failed": "Coupon failed",
    "prior_order_count": "Previous orders",
    "prior_abandonment_count": "Previous abandonments",
    "prior_return_count": "Previous returns",
    "prior_rto_count": "Previous RTOs",
    "prior_return_rate": "Previous return rate",
    "prior_rto_rate": "Previous RTO rate",
    "payment_method": "Payment method",
    "device_type": "Device",
    "checkout_stage": "Checkout stage",
    "primary_reason": "Diagnosed reason",
    "action": "Recovery action",
    "order_value": "Order value",
    "product_price": "Product price",
    "quantity": "Quantity",
    "weight_kg": "Product weight",
    "has_size_variants": "Product has sizes",
    "is_cod": "Cash on delivery",
    "category": "Product category",
    "courier": "Courier",
    "city": "Delivery city",
    "promised_days": "Promised delivery days",
    "voc_review_count": "Reviews on this product",
    "voc_avg_rating": "Product rating",
    "voc_size_fit_rate": "Size/fit complaints in reviews",
    "voc_quality_rate": "Quality complaints in reviews",
    "voc_delivery_rate": "Delivery complaints in reviews",
    "voc_packaging_rate": "Packaging complaints in reviews",
}


def label_for(feature: str) -> str:
    return FEATURE_LABELS.get(feature, feature.replace("_", " ").capitalize())


@dataclass
class Contribution:
    feature: str
    label: str
    value: Any
    contribution: float          # signed, in log-odds
    direction: str               # INCREASES / DECREASES
    percent_of_total: float      # share of total absolute movement

    def to_dict(self) -> dict[str, Any]:
        val = self.value
        if isinstance(val, (np.floating, np.integer)):
            val = val.item()
        if isinstance(val, float):
            val = round(val, 4)
        return {
            "feature": self.feature,
            "label": self.label,
            "value": val,
            "contribution": round(self.contribution, 4),
            "direction": self.direction,
            "percent_of_total": round(self.percent_of_total, 2),
        }


class ShapExplainer:
    """Cached SHAP TreeExplainer for one fitted pipeline."""

    _cache: dict[int, Any] = {}
    _lock = threading.Lock()

    @classmethod
    def _get(cls, pipeline: Pipeline) -> Any:
        key = id(pipeline)
        if key in cls._cache:
            return cls._cache[key]
        with cls._lock:
            if key in cls._cache:
                return cls._cache[key]
            import shap

            explainer = shap.TreeExplainer(pipeline.named_steps["clf"])
            cls._cache[key] = explainer
            return explainer

    @classmethod
    def clear(cls) -> None:
        with cls._lock:
            cls._cache.clear()


def _source_feature(expanded_name: str, source_features: list[str]) -> tuple[str, str | None]:
    """Map an encoded column back to (source feature, category value)."""
    if expanded_name in source_features:
        return expanded_name, None
    # OneHotEncoder emits "<feature>_<category>"; match the longest source name.
    best = ""
    for f in source_features:
        if expanded_name.startswith(f + "_") and len(f) > len(best):
            best = f
    if best:
        return best, expanded_name[len(best) + 1:]
    # "infrequent_sklearn" and similar fall back to the raw name.
    return re.sub(r"_[^_]*$", "", expanded_name) or expanded_name, None


def explain_row(
    pipeline: Pipeline,
    row: pd.DataFrame,
    source_features: list[str],
    top_n: int = 6,
) -> list[Contribution]:
    """Per-feature SHAP contributions for a single scored row."""
    pre = pipeline.named_steps["pre"]
    transformed = pre.transform(row)
    expanded = list(pre.get_feature_names_out())

    explainer = ShapExplainer._get(pipeline)
    values = explainer.shap_values(transformed)
    arr = np.asarray(values)
    if arr.ndim == 3:            # (n, features, classes) -> positive class
        arr = arr[0, :, -1]
    elif arr.ndim == 2:
        arr = arr[0]
    arr = np.asarray(arr, dtype=float).ravel()

    # Fold one-hot columns back onto their source feature.
    folded: dict[str, float] = {}
    chosen_value: dict[str, Any] = {}
    for name, contrib in zip(expanded, arr):
        src, category = _source_feature(name, source_features)
        folded[src] = folded.get(src, 0.0) + float(contrib)
        if category is not None and abs(float(contrib)) > 1e-12:
            idx = expanded.index(name)
            if transformed[0][idx] > 0:      # this is the active category
                chosen_value[src] = category

    total = sum(abs(v) for v in folded.values()) or 1.0
    contributions: list[Contribution] = []
    for feature, contrib in folded.items():
        if abs(contrib) < 1e-9:
            continue
        raw = chosen_value.get(feature)
        if raw is None and feature in row.columns:
            raw = row.iloc[0][feature]
        contributions.append(
            Contribution(
                feature=feature,
                label=label_for(feature),
                value=raw,
                contribution=float(contrib),
                direction="INCREASES" if contrib > 0 else "DECREASES",
                percent_of_total=abs(contrib) / total * 100.0,
            )
        )

    contributions.sort(key=lambda c: -abs(c.contribution))
    return contributions[:top_n]


def global_importance(
    pipeline: Pipeline,
    X: pd.DataFrame,
    y,
    source_features: list[str],
    n_repeats: int = 5,
    sample: int = 4000,
    random_state: int = 42,
) -> list[dict[str, Any]]:
    """Permutation importance on the source (pre-encoding) columns."""
    from sklearn.inspection import permutation_importance

    if len(X) > sample:
        X = X.sample(sample, random_state=random_state)
        y = y.loc[X.index]

    result = permutation_importance(
        pipeline, X, y, n_repeats=n_repeats, random_state=random_state,
        scoring="roc_auc", n_jobs=1,
    )
    rows = [
        {
            "feature": f,
            "label": label_for(f),
            "importance": round(float(result.importances_mean[i]), 5),
            "std": round(float(result.importances_std[i]), 5),
        }
        for i, f in enumerate(source_features)
    ]
    rows.sort(key=lambda r: -r["importance"])
    return rows
