"""The central decision engine.

One engine serves both pillars. It takes customer context, model predictions,
review intelligence and business economics, enumerates every candidate action,
prices each one, and returns the action with the highest expected incremental
profit -- together with the full comparison, so a human can see what was
rejected and why.

    context + predictions + review signals + economics
        -> candidate actions
        -> expected profit per action
        -> NEXT BEST ACTION (+ ranked alternatives)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..common import ModelStore
from ..recovery import recovery_model
from ..recovery.reason_engine import diagnose
from .economics import (
    ASSUMPTION_DISCLOSURE,
    PROTECTION_ACTIONS,
    RECOVERY_ACTIONS,
    CostModel,
)
from .profit_optimizer import (
    ActionEconomics,
    evaluate_protection_action,
    evaluate_recovery_action,
    rank,
)

# Review-derived signals that should force a protection action onto the
# shortlist even when the model score alone would not have surfaced it.
_VOC_FORCED_ACTIONS = {
    "SIZE_FIT": "SIZE_RECOMMENDATION",
    "PACKAGING": "PACKAGING_REVIEW",
    "DELIVERY": "DELIVERY_ESCALATION",
}


@dataclass
class Decision:
    pillar: str
    next_best_action: ActionEconomics
    alternatives: list[ActionEconomics] = field(default_factory=list)
    rationale: str = ""
    inputs: dict[str, Any] = field(default_factory=dict)
    disclosures: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "pillar": self.pillar,
            "next_best_action": self.next_best_action.to_dict(),
            "alternatives": [a.to_dict() for a in self.alternatives],
            "rationale": self.rationale,
            "inputs": self.inputs,
            "disclosures": self.disclosures,
        }


# --------------------------------------------------------------------------
# Recovery
# --------------------------------------------------------------------------
def decide_recovery(
    session: dict[str, Any],
    store: ModelStore,
    costs: CostModel,
    actions: list[str] | None = None,
) -> Decision:
    """Choose the recovery action with the highest expected incremental profit."""
    actions = actions or RECOVERY_ACTIONS
    cart_value = float(session.get("cart_value") or 0.0)
    shipping = float(session.get("shipping_cost") or 0.0)

    probabilities = recovery_model.predict_all_actions(session, store, actions)
    baseline = probabilities.get("NO_ACTION", 0.0)

    options = [
        evaluate_recovery_action(
            action=a,
            probability=probabilities[a],
            baseline_probability=baseline,
            cart_value=cart_value,
            shipping_cost=shipping,
            costs=costs,
        )
        for a in actions
    ]
    ranked = rank(options)
    best = ranked[0]

    reason = diagnose(session)
    highest_conversion = max(options, key=lambda o: o.probability)

    if best.action == "NO_ACTION":
        rationale = (
            "No outreach clears its own cost on this cart: every candidate action "
            "spends more than the margin it is expected to add."
        )
    elif highest_conversion.action != best.action:
        rationale = (
            f"{best.label} is chosen on expected profit (Rs {best.expected_profit:,.2f}). "
            f"{highest_conversion.label} would convert more often "
            f"({highest_conversion.probability * 100:.1f}% vs {best.probability * 100:.1f}%) "
            f"but returns Rs {highest_conversion.expected_profit:,.2f} after its "
            f"Rs {highest_conversion.total_cost:,.2f} cost, so it is rejected."
        )
    else:
        rationale = (
            f"{best.label} maximises both conversion and expected profit "
            f"(Rs {best.expected_profit:,.2f} on a Rs {best.total_cost:,.2f} spend)."
        )
    rationale += f" Diagnosed cause: {reason.label.lower()}."

    return Decision(
        pillar="RECOVERY",
        next_best_action=best,
        alternatives=ranked[1:],
        rationale=rationale,
        inputs={
            "cart_value": cart_value,
            "shipping_cost": shipping,
            "baseline_recovery_probability": round(baseline, 4),
            "diagnosed_reason": reason.to_dict(),
            "gross_margin": costs.gross_margin,
        },
        disclosures=[ASSUMPTION_DISCLOSURE],
    )


# --------------------------------------------------------------------------
# Protection
# --------------------------------------------------------------------------
def decide_protection(
    order: dict[str, Any],
    rto_probability: float,
    return_probability: float,
    costs: CostModel,
    voc_signals: list[str] | None = None,
    actions: list[str] | None = None,
) -> Decision:
    """Choose the protection action with the highest expected avoided loss."""
    candidates = list(actions or PROTECTION_ACTIONS)
    order_value = float(order.get("order_value") or 0.0)
    is_cod = bool(order.get("is_cod"))

    # A prepaid order has nothing to convert.
    if not is_cod and "PAYMENT_CONFIRMATION" in candidates:
        candidates.remove("PAYMENT_CONFIRMATION")

    forced: list[str] = []
    for signal in voc_signals or []:
        action = _VOC_FORCED_ACTIONS.get(signal)
        if action and action not in candidates:
            candidates.append(action)
        if action:
            forced.append(action)

    options = [
        evaluate_protection_action(
            action=a,
            rto_probability=rto_probability,
            return_probability=return_probability,
            order_value=order_value,
            costs=costs,
        )
        for a in candidates
    ]
    ranked = rank(options)
    best = ranked[0]

    if best.action == "NO_ACTION":
        rationale = (
            "Risk on this order is low enough that no protection step pays for "
            "itself; the expected avoided loss is smaller than the cost of acting."
        )
    else:
        rationale = (
            f"{best.label} is chosen: it is expected to avoid "
            f"Rs {best.expected_revenue:,.2f} of loss for Rs {best.total_cost:,.2f}, "
            f"a net Rs {best.expected_profit:,.2f}."
        )
    if forced:
        rationale += (
            " Customer reviews for this product raised "
            + ", ".join(sorted(set(forced))).replace("_", " ").lower()
            + " as a live concern, so it was included in the comparison."
        )

    return Decision(
        pillar="PROTECTION",
        next_best_action=best,
        alternatives=ranked[1:],
        rationale=rationale,
        inputs={
            "order_value": order_value,
            "is_cod": is_cod,
            "rto_probability": round(rto_probability, 4),
            "return_probability": round(return_probability, 4),
            "voc_signals": voc_signals or [],
            "rto_loss_if_event": round(costs.rto_loss(), 2),
            "return_loss_if_event": round(costs.return_loss(order_value), 2),
        },
        disclosures=[ASSUMPTION_DISCLOSURE],
    )
