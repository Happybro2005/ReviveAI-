"""Business economics for the decision engine.

Every number here is an explicit, inspectable assumption. Two categories exist
and the platform keeps them clearly apart:

LEARNED    Recovery uplift comes from the trained recovery model: the historical
           data contains carts that received each action (including none), so
           the incremental effect of an action is estimated from outcomes.

ASSUMED    Protection-action effectiveness is NOT learned. The dataset contains
           no historical protection interventions, so there is nothing to learn
           an uplift from. These are stated planning assumptions, exposed in the
           API response under `assumption_basis` so no one mistakes them for
           measured results. Change them here, not in the calling code.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# --------------------------------------------------------------------------
# Recovery actions
# --------------------------------------------------------------------------
RECOVERY_ACTIONS = [
    "NO_ACTION",
    "PERSONALIZED_REMINDER",
    "PAYMENT_ASSISTANCE",
    "FREE_SHIPPING",
    "DISCOUNT_5",
    "DISCOUNT_10",
    "TECH_SUPPORT",
]

RECOVERY_ACTION_LABELS = {
    "NO_ACTION": "No action",
    "PERSONALIZED_REMINDER": "Personalised reminder",
    "PAYMENT_ASSISTANCE": "Payment assistance",
    "FREE_SHIPPING": "Free shipping offer",
    "DISCOUNT_5": "5% discount",
    "DISCOUNT_10": "10% discount",
    "TECH_SUPPORT": "Technical support outreach",
}

CHANNEL_BY_ACTION = {
    "NO_ACTION": "NONE",
    "PERSONALIZED_REMINDER": "EMAIL",
    "PAYMENT_ASSISTANCE": "WHATSAPP",
    "FREE_SHIPPING": "EMAIL",
    "DISCOUNT_5": "SMS",
    "DISCOUNT_10": "SMS",
    "TECH_SUPPORT": "CALL",
}

# Discount rate applied to cart value, charged only when the cart converts.
DISCOUNT_RATE = {"DISCOUNT_5": 0.05, "DISCOUNT_10": 0.10}

# Actions that waive the shipping charge (cost incurred only on conversion).
SUBSIDISES_SHIPPING = {"FREE_SHIPPING"}


@dataclass
class CostModel:
    """Per-message and per-touch costs, in INR."""

    email: float = 0.50
    sms: float = 0.25
    whatsapp: float = 0.35
    call: float = 18.00
    manual_review: float = 45.00
    gross_margin: float = 0.35

    # Fulfilment costs used to value a prevented RTO or return.
    rto_logistics_loss: float = 190.0   # forward + reverse leg, unrecovered
    rto_handling_loss: float = 60.0     # re-inwarding, QC, restock labour
    return_logistics_loss: float = 130.0
    return_restock_loss: float = 55.0
    # Share of margin lost when a returned item cannot be resold at full price.
    return_margin_erosion: float = 0.25

    def channel_cost(self, channel: str) -> float:
        return {
            "EMAIL": self.email,
            "SMS": self.sms,
            "WHATSAPP": self.whatsapp,
            "CALL": self.call,
            "MANUAL": self.manual_review,
            "NONE": 0.0,
        }.get(channel.upper(), 0.0)

    def rto_loss(self) -> float:
        return self.rto_logistics_loss + self.rto_handling_loss

    def return_loss(self, order_value: float) -> float:
        return (
            self.return_logistics_loss
            + self.return_restock_loss
            + order_value * self.gross_margin * self.return_margin_erosion
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "email": self.email, "sms": self.sms, "whatsapp": self.whatsapp,
            "call": self.call, "manual_review": self.manual_review,
            "gross_margin": self.gross_margin,
            "rto_logistics_loss": self.rto_logistics_loss,
            "rto_handling_loss": self.rto_handling_loss,
            "return_logistics_loss": self.return_logistics_loss,
            "return_restock_loss": self.return_restock_loss,
            "return_margin_erosion": self.return_margin_erosion,
        }


# --------------------------------------------------------------------------
# Protection actions -- ASSUMED effectiveness (see module docstring)
# --------------------------------------------------------------------------
PROTECTION_ACTIONS = [
    "NO_ACTION",
    "ORDER_CONFIRMATION",
    "PAYMENT_CONFIRMATION",
    "MANUAL_REVIEW",
    "LOGISTICS_REVIEW",
    "SIZE_RECOMMENDATION",
    "PACKAGING_REVIEW",
    "DELIVERY_ESCALATION",
]

PROTECTION_ACTION_LABELS = {
    "NO_ACTION": "No action",
    "ORDER_CONFIRMATION": "Confirm order with customer",
    "PAYMENT_CONFIRMATION": "Request prepayment / convert from COD",
    "MANUAL_REVIEW": "Route to manual review",
    "LOGISTICS_REVIEW": "Logistics / courier review",
    "SIZE_RECOMMENDATION": "Send size recommendation",
    "PACKAGING_REVIEW": "Upgrade packaging for this shipment",
    "DELIVERY_ESCALATION": "Escalate delivery with courier",
}


@dataclass
class ProtectionAction:
    """`rto_reduction` / `return_reduction` are relative risk reductions."""

    action: str
    channel: str
    rto_reduction: float = 0.0
    return_reduction: float = 0.0
    fixed_cost: float = 0.0
    basis: str = ""


# Effectiveness assumptions. Sourced from published industry ranges for COD
# confirmation and pre-purchase sizing guidance; treated as planning inputs.
PROTECTION_EFFECTS: dict[str, ProtectionAction] = {
    "NO_ACTION": ProtectionAction(
        "NO_ACTION", "NONE", 0.0, 0.0, 0.0, "Baseline; no cost, no effect."
    ),
    "ORDER_CONFIRMATION": ProtectionAction(
        "ORDER_CONFIRMATION", "WHATSAPP", rto_reduction=0.35, fixed_cost=0.35,
        basis="Assumed 35% relative RTO reduction from an explicit confirmation touch.",
    ),
    "PAYMENT_CONFIRMATION": ProtectionAction(
        "PAYMENT_CONFIRMATION", "WHATSAPP", rto_reduction=0.55, fixed_cost=0.35,
        basis="Assumed 55% relative RTO reduction when a COD order is converted to prepaid.",
    ),
    "MANUAL_REVIEW": ProtectionAction(
        "MANUAL_REVIEW", "MANUAL", rto_reduction=0.60, return_reduction=0.25,
        fixed_cost=45.0,
        basis="Assumed 60% RTO / 25% return reduction; carries a full analyst-touch cost.",
    ),
    "LOGISTICS_REVIEW": ProtectionAction(
        "LOGISTICS_REVIEW", "MANUAL", rto_reduction=0.20, return_reduction=0.10,
        fixed_cost=25.0,
        basis="Assumed 20% RTO reduction from re-routing to a better-performing courier.",
    ),
    "SIZE_RECOMMENDATION": ProtectionAction(
        "SIZE_RECOMMENDATION", "EMAIL", return_reduction=0.25, fixed_cost=0.50,
        basis="Assumed 25% relative reduction in size-driven returns from proactive fit guidance.",
    ),
    "PACKAGING_REVIEW": ProtectionAction(
        "PACKAGING_REVIEW", "MANUAL", return_reduction=0.30, fixed_cost=12.0,
        basis="Assumed 30% reduction in damage-driven returns from upgraded packaging.",
    ),
    "DELIVERY_ESCALATION": ProtectionAction(
        "DELIVERY_ESCALATION", "MANUAL", rto_reduction=0.18, return_reduction=0.08,
        fixed_cost=15.0,
        basis="Assumed 18% RTO reduction from proactive delivery escalation on delayed lanes.",
    ),
}

ASSUMPTION_DISCLOSURE = (
    "Recovery uplift is estimated by the trained recovery model from historical "
    "outcomes. Protection-action effectiveness is a stated planning assumption, "
    "not a measured result: the dataset contains no historical protection "
    "interventions to learn an uplift from."
)
