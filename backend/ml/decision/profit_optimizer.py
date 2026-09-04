"""Expected-profit arithmetic.

The objective is MAXIMUM EXPECTED INCREMENTAL PROFIT, not maximum conversion.
That distinction is the whole point: a 10% discount usually wins on conversion
and frequently loses on profit, because it pays margin away on carts that would
have converted anyway.

Recovery formulas
-----------------
    uplift              = p(action) - p(NO_ACTION)
    incremental_revenue = cart_value * uplift
    gross_profit        = incremental_revenue * gross_margin
    discount_cost       = cart_value * discount_rate * p(action)     [paid on conversion]
    shipping_subsidy    = shipping_cost * p(action)                  [paid on conversion]
    comms_cost          = channel cost                               [paid regardless]
    total_cost          = discount_cost + shipping_subsidy + comms_cost
    expected_profit     = gross_profit - total_cost
    roi                 = expected_profit / total_cost * 100         [null when cost = 0]

Note that discount and subsidy are charged against p(action), not against the
uplift: a discount is honoured by every customer who redeems it, including the
ones who would have bought anyway. Charging it only against the uplift would
flatter discounts, which is exactly the error this optimizer exists to avoid.

Protection formulas
-------------------
    avoided_loss    = loss_if_event * p(event) * relative_reduction
    expected_profit = avoided_loss - action_cost
    roi             = expected_profit / action_cost * 100            [null when cost = 0]
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .economics import (
    CHANNEL_BY_ACTION,
    DISCOUNT_RATE,
    PROTECTION_ACTION_LABELS,
    PROTECTION_EFFECTS,
    RECOVERY_ACTION_LABELS,
    SUBSIDISES_SHIPPING,
    CostModel,
)


@dataclass
class ActionEconomics:
    action: str
    label: str
    channel: str
    probability: float              # p(success | action)
    baseline_probability: float
    uplift: float
    expected_revenue: float
    incremental_revenue: float
    gross_profit: float
    discount_cost: float
    shipping_subsidy: float
    comms_cost: float
    total_cost: float
    expected_profit: float
    roi: float | None
    notes: str = ""
    breakdown: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "label": self.label,
            "channel": self.channel,
            "probability": round(self.probability, 4),
            "baseline_probability": round(self.baseline_probability, 4),
            "uplift": round(self.uplift, 4),
            "expected_revenue": round(self.expected_revenue, 2),
            "incremental_revenue": round(self.incremental_revenue, 2),
            "gross_profit": round(self.gross_profit, 2),
            "discount_cost": round(self.discount_cost, 2),
            "shipping_subsidy": round(self.shipping_subsidy, 2),
            "comms_cost": round(self.comms_cost, 2),
            "total_cost": round(self.total_cost, 2),
            "expected_profit": round(self.expected_profit, 2),
            "roi": round(self.roi, 2) if self.roi is not None else None,
            "notes": self.notes,
            "breakdown": self.breakdown,
        }


def evaluate_recovery_action(
    action: str,
    probability: float,
    baseline_probability: float,
    cart_value: float,
    shipping_cost: float,
    costs: CostModel,
) -> ActionEconomics:
    """Expected incremental profit of one recovery action on one cart."""
    channel = CHANNEL_BY_ACTION.get(action, "NONE")
    discount_rate = DISCOUNT_RATE.get(action, 0.0)

    uplift = probability - baseline_probability
    expected_revenue = cart_value * probability
    incremental_revenue = cart_value * uplift
    gross_profit = incremental_revenue * costs.gross_margin

    discount_cost = cart_value * discount_rate * probability
    shipping_subsidy = shipping_cost * probability if action in SUBSIDISES_SHIPPING else 0.0
    comms_cost = costs.channel_cost(channel)

    total_cost = discount_cost + shipping_subsidy + comms_cost
    expected_profit = gross_profit - total_cost
    roi = (expected_profit / total_cost * 100.0) if total_cost > 0 else None

    if action == "NO_ACTION":
        notes = "Baseline: no outreach, no cost. Every other action is measured against this."
    elif uplift <= 0:
        notes = "This action is not predicted to lift conversion above the do-nothing baseline."
    else:
        notes = (
            f"Lifts conversion by {uplift * 100:.1f} points over doing nothing, "
            f"at a total expected cost of Rs {total_cost:,.2f}."
        )

    return ActionEconomics(
        action=action,
        label=RECOVERY_ACTION_LABELS.get(action, action),
        channel=channel,
        probability=probability,
        baseline_probability=baseline_probability,
        uplift=uplift,
        expected_revenue=expected_revenue,
        incremental_revenue=incremental_revenue,
        gross_profit=gross_profit,
        discount_cost=discount_cost,
        shipping_subsidy=shipping_subsidy,
        comms_cost=comms_cost,
        total_cost=total_cost,
        expected_profit=expected_profit,
        roi=roi,
        notes=notes,
        breakdown={
            "formula": "profit = cart_value * uplift * margin - discount - subsidy - comms",
            "cart_value": round(cart_value, 2),
            "gross_margin": costs.gross_margin,
            "discount_rate": discount_rate,
        },
    )


def evaluate_protection_action(
    action: str,
    rto_probability: float,
    return_probability: float,
    order_value: float,
    costs: CostModel,
) -> ActionEconomics:
    """Expected profit of one protection action on one order."""
    effect = PROTECTION_EFFECTS.get(action)
    if effect is None:
        raise ValueError(f"Unknown protection action: {action}")

    rto_loss = costs.rto_loss()
    ret_loss = costs.return_loss(order_value)

    avoided_rto = rto_loss * rto_probability * effect.rto_reduction
    avoided_return = ret_loss * return_probability * effect.return_reduction
    avoided_total = avoided_rto + avoided_return

    total_cost = effect.fixed_cost
    expected_profit = avoided_total - total_cost
    roi = (expected_profit / total_cost * 100.0) if total_cost > 0 else None

    combined_reduction = effect.rto_reduction + effect.return_reduction
    notes = effect.basis or "No effect assumed."

    return ActionEconomics(
        action=action,
        label=PROTECTION_ACTION_LABELS.get(action, action),
        channel=effect.channel,
        probability=combined_reduction,
        baseline_probability=0.0,
        uplift=combined_reduction,
        expected_revenue=avoided_total,
        incremental_revenue=avoided_total,
        gross_profit=avoided_total,
        discount_cost=0.0,
        shipping_subsidy=0.0,
        comms_cost=total_cost,
        total_cost=total_cost,
        expected_profit=expected_profit,
        roi=roi,
        notes=notes,
        breakdown={
            "formula": "profit = loss_if_event * p(event) * reduction - action_cost",
            "avoided_rto_loss": round(avoided_rto, 2),
            "avoided_return_loss": round(avoided_return, 2),
            "rto_loss_if_event": round(rto_loss, 2),
            "return_loss_if_event": round(ret_loss, 2),
            "rto_reduction": effect.rto_reduction,
            "return_reduction": effect.return_reduction,
            "effect_basis": "ASSUMED",
        },
    )


def rank(options: list[ActionEconomics]) -> list[ActionEconomics]:
    """Best expected profit first; ROI breaks ties so cheap wins beat costly ones."""
    return sorted(
        options,
        key=lambda o: (-o.expected_profit, -(o.roi if o.roi is not None else 0.0)),
    )
