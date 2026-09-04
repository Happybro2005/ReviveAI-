"""Abandonment reason diagnosis from behavioural evidence.

This is deliberately a transparent evidence engine rather than a black-box
classifier: a seller acting on "high shipping cost" needs to see the numbers
that produced that verdict. Every rule reports the observation that fired it,
the threshold it was compared against, and how strongly it weighs.

Confidence is the winning reason's share of total fired evidence weight, so a
cart with one unambiguous cause scores high and a cart with several competing
causes scores lower -- which is the honest answer in that situation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

REASONS = [
    "PAYMENT_FAILURE",
    "HIGH_SHIPPING_COST",
    "PRICE_CONCERN",
    "COUPON_ISSUE",
    "TECHNICAL_PROBLEM",
    "CUSTOMER_HESITATION",
    "OTHER",
]

REASON_LABELS = {
    "PAYMENT_FAILURE": "Payment failure",
    "HIGH_SHIPPING_COST": "High shipping cost",
    "PRICE_CONCERN": "Price concern",
    "COUPON_ISSUE": "Coupon problem",
    "TECHNICAL_PROBLEM": "Technical problem",
    "CUSTOMER_HESITATION": "Customer hesitation",
    "OTHER": "Undetermined",
}

# Shipping above this share of cart value is treated as a deterrent.
SHIPPING_RATIO_WARN = 0.08
SHIPPING_RATIO_HIGH = 0.12
HIGH_VALUE_CART = 15000.0


@dataclass
class Evidence:
    code: str
    description: str
    observed: str
    weight: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "description": self.description,
            "observed": self.observed,
            "weight": round(self.weight, 3),
        }


@dataclass
class ReasonDiagnosis:
    primary_reason: str
    label: str
    confidence: float
    evidence: list[Evidence] = field(default_factory=list)
    alternatives: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "primary_reason": self.primary_reason,
            "label": self.label,
            "confidence": round(self.confidence, 4),
            "evidence": [e.to_dict() for e in self.evidence],
            "alternatives": self.alternatives,
        }


def _fmt_money(v: float) -> str:
    return f"Rs {v:,.0f}"


def diagnose(features: dict[str, Any]) -> ReasonDiagnosis:
    """Diagnose why a checkout was (or is about to be) abandoned."""
    cart_value = float(features.get("cart_value") or 0.0)
    shipping = float(features.get("shipping_cost") or 0.0)
    ratio = float(features.get("shipping_cart_ratio") or 0.0)
    if not ratio and cart_value:
        ratio = shipping / cart_value
    attempts = int(features.get("payment_attempts") or 0)
    payment_failed = bool(features.get("payment_failed"))
    coupon_applied = bool(features.get("coupon_applied"))
    coupon_failed = bool(features.get("coupon_failed"))
    page_errors = int(features.get("page_errors") or 0)
    address_edits = int(features.get("address_edits") or 0)
    stage = str(features.get("checkout_stage") or "").upper()
    duration = int(features.get("session_duration_sec") or 0)
    prior_abandons = int(features.get("prior_abandonment_count") or 0)
    prior_orders = int(features.get("prior_order_count") or 0)

    scores: dict[str, float] = {r: 0.0 for r in REASONS}
    evidence: dict[str, list[Evidence]] = {r: [] for r in REASONS}

    def add(reason: str, code: str, desc: str, observed: str, weight: float) -> None:
        scores[reason] += weight
        evidence[reason].append(Evidence(code, desc, observed, weight))

    # --- payment ---
    if payment_failed:
        add("PAYMENT_FAILURE", "PAYMENT_DECLINED",
            "The payment attempt was declined at the gateway.",
            "Payment failed = yes", 3.0)
    if attempts >= 2:
        add("PAYMENT_FAILURE", "REPEATED_ATTEMPTS",
            "The customer retried payment multiple times.",
            f"{attempts} payment attempts", 1.2 * min(attempts - 1, 3))

    # --- shipping ---
    if ratio >= SHIPPING_RATIO_HIGH:
        add("HIGH_SHIPPING_COST", "SHIPPING_RATIO_HIGH",
            f"Shipping is {ratio * 100:.1f}% of cart value, above the "
            f"{SHIPPING_RATIO_HIGH * 100:.0f}% deterrent threshold.",
            f"Shipping {_fmt_money(shipping)} on a {_fmt_money(cart_value)} cart "
            f"= {ratio * 100:.1f}%", 3.0)
    elif ratio >= SHIPPING_RATIO_WARN:
        add("HIGH_SHIPPING_COST", "SHIPPING_RATIO_ELEVATED",
            f"Shipping is {ratio * 100:.1f}% of cart value, an elevated share.",
            f"Shipping {_fmt_money(shipping)} on a {_fmt_money(cart_value)} cart "
            f"= {ratio * 100:.1f}%", 1.5)
    if stage == "SHIPPING" and shipping > 0:
        add("HIGH_SHIPPING_COST", "DROPPED_AT_SHIPPING",
            "The customer left at the step where shipping cost is revealed.",
            "Last stage reached: SHIPPING", 1.2)

    # --- coupon ---
    if coupon_failed:
        add("COUPON_ISSUE", "COUPON_REJECTED",
            "An applied coupon was rejected.",
            "Coupon failed = yes", 2.6)
    elif coupon_applied and stage in ("PAYMENT", "REVIEW"):
        add("PRICE_CONCERN", "COUPON_SEEKING",
            "The customer applied a coupon before leaving, indicating price focus.",
            "Coupon applied = yes", 0.8)

    # --- technical ---
    if page_errors >= 2:
        add("TECHNICAL_PROBLEM", "PAGE_ERRORS",
            "Multiple client errors occurred during checkout.",
            f"{page_errors} page errors", 1.3 * min(page_errors, 4))
    elif page_errors == 1:
        add("TECHNICAL_PROBLEM", "PAGE_ERROR",
            "A client error occurred during checkout.",
            "1 page error", 1.0)

    # --- price ---
    if cart_value >= HIGH_VALUE_CART and stage in ("REVIEW", "PAYMENT"):
        add("PRICE_CONCERN", "HIGH_VALUE_HESITATION",
            "A high-value cart was left at the final confirmation step.",
            f"Cart {_fmt_money(cart_value)} at stage {stage}", 1.4)
    if duration > 900 and cart_value > 5000:
        add("PRICE_CONCERN", "LONG_DELIBERATION",
            "The customer spent an unusually long time before leaving.",
            f"{duration // 60} minutes in checkout", 1.0)

    # --- hesitation ---
    if stage in ("CART", "ADDRESS"):
        add("CUSTOMER_HESITATION", "EARLY_STAGE_EXIT",
            "The customer left before reaching payment.",
            f"Last stage reached: {stage}", 1.8)
    if prior_abandons >= 2:
        add("CUSTOMER_HESITATION", "REPEAT_ABANDONER",
            "This customer has abandoned checkout before.",
            f"{prior_abandons} previous abandonments", 0.6 * min(prior_abandons, 4))
    if address_edits >= 2:
        add("CUSTOMER_HESITATION", "ADDRESS_UNCERTAINTY",
            "The customer repeatedly edited the delivery address.",
            f"{address_edits} address edits", 0.9)
    if duration < 90 and prior_orders == 0:
        add("CUSTOMER_HESITATION", "BROWSING_INTENT",
            "A short first-time session suggests browsing rather than buying.",
            f"{duration}s session, no previous orders", 0.9)

    fired = {r: s for r, s in scores.items() if s > 0}
    if not fired:
        return ReasonDiagnosis(
            primary_reason="OTHER",
            label=REASON_LABELS["OTHER"],
            confidence=0.0,
            evidence=[
                Evidence(
                    "NO_STRONG_SIGNAL",
                    "No single behavioural signal stood out for this checkout.",
                    "All diagnostic thresholds below trigger level",
                    0.0,
                )
            ],
        )

    total = sum(fired.values())
    ranked = sorted(fired.items(), key=lambda kv: -kv[1])
    top_reason, top_score = ranked[0]

    return ReasonDiagnosis(
        primary_reason=top_reason,
        label=REASON_LABELS[top_reason],
        confidence=top_score / total,
        evidence=evidence[top_reason],
        alternatives=[
            {
                "reason": r,
                "label": REASON_LABELS[r],
                "confidence": round(s / total, 4),
                "evidence": [e.to_dict() for e in evidence[r]],
            }
            for r, s in ranked[1:4]
        ],
    )
