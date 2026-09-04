"""Revenue recovery simulator.

Pure arithmetic over seller-supplied planning inputs -- no model involved, and
deliberately so: this answers "what would recovery be worth at these rates?",
which is a business question, not a prediction. Every intermediate value is
returned so the numbers can be checked by hand.

    abandoned_checkouts = checkout_volume * abandonment_rate
    revenue_at_risk     = abandoned_checkouts * average_order_value
    recovered_orders    = abandoned_checkouts * recovery_rate
    recovered_revenue   = recovered_orders * average_order_value
    gross_profit        = recovered_revenue * gross_margin
    discount_cost       = recovered_revenue * discount_rate
    delivery_cost       = recovered_orders * delivery_cost_per_order
    outreach_cost       = abandoned_checkouts * intervention_cost_per_contact
    total_cost          = discount_cost + delivery_cost + outreach_cost
    net_profit          = gross_profit - total_cost
    roi                 = net_profit / total_cost * 100      [null when cost = 0]

Outreach is charged on every abandoned checkout contacted, not only the ones
that convert, because that is what actually happens when you send the messages.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class SimulatorInputError(ValueError):
    """Raised for out-of-range or nonsensical simulator inputs."""


@dataclass
class SimulatorInputs:
    checkout_volume: int
    average_order_value: float
    abandonment_rate: float          # 0..1
    recovery_rate: float             # 0..1
    discount_rate: float = 0.0       # 0..1
    gross_margin: float = 0.35       # 0..1
    delivery_cost_per_order: float = 0.0
    intervention_cost_per_contact: float = 0.0
    contact_coverage: float = 1.0    # share of abandoned carts actually contacted

    def validate(self) -> None:
        if self.checkout_volume < 0:
            raise SimulatorInputError("checkout_volume must be zero or positive.")
        if self.average_order_value < 0:
            raise SimulatorInputError("average_order_value must be zero or positive.")
        for name, value in (
            ("abandonment_rate", self.abandonment_rate),
            ("recovery_rate", self.recovery_rate),
            ("discount_rate", self.discount_rate),
            ("gross_margin", self.gross_margin),
            ("contact_coverage", self.contact_coverage),
        ):
            if not 0.0 <= value <= 1.0:
                raise SimulatorInputError(f"{name} must be between 0 and 1 (got {value}).")
        if self.delivery_cost_per_order < 0:
            raise SimulatorInputError("delivery_cost_per_order must be zero or positive.")
        if self.intervention_cost_per_contact < 0:
            raise SimulatorInputError(
                "intervention_cost_per_contact must be zero or positive."
            )


def simulate(inputs: SimulatorInputs) -> dict[str, Any]:
    inputs.validate()

    abandoned = inputs.checkout_volume * inputs.abandonment_rate
    revenue_at_risk = abandoned * inputs.average_order_value
    contacted = abandoned * inputs.contact_coverage
    recovered_orders = abandoned * inputs.recovery_rate
    recovered_revenue = recovered_orders * inputs.average_order_value

    gross_profit = recovered_revenue * inputs.gross_margin
    discount_cost = recovered_revenue * inputs.discount_rate
    delivery_cost = recovered_orders * inputs.delivery_cost_per_order
    outreach_cost = contacted * inputs.intervention_cost_per_contact
    total_cost = discount_cost + delivery_cost + outreach_cost

    net_profit = gross_profit - total_cost
    roi = (net_profit / total_cost * 100.0) if total_cost > 0 else None

    unrecovered = revenue_at_risk - recovered_revenue

    return {
        "inputs": {
            "checkout_volume": inputs.checkout_volume,
            "average_order_value": inputs.average_order_value,
            "abandonment_rate": inputs.abandonment_rate,
            "recovery_rate": inputs.recovery_rate,
            "discount_rate": inputs.discount_rate,
            "gross_margin": inputs.gross_margin,
            "delivery_cost_per_order": inputs.delivery_cost_per_order,
            "intervention_cost_per_contact": inputs.intervention_cost_per_contact,
            "contact_coverage": inputs.contact_coverage,
        },
        "abandoned_checkouts": round(abandoned, 2),
        "contacted_checkouts": round(contacted, 2),
        "revenue_at_risk": round(revenue_at_risk, 2),
        "recovered_orders": round(recovered_orders, 2),
        "recovered_revenue": round(recovered_revenue, 2),
        "unrecovered_revenue": round(unrecovered, 2),
        "gross_profit": round(gross_profit, 2),
        "discount_cost": round(discount_cost, 2),
        "delivery_cost": round(delivery_cost, 2),
        "outreach_cost": round(outreach_cost, 2),
        "total_cost": round(total_cost, 2),
        "net_profit": round(net_profit, 2),
        "roi_percent": round(roi, 2) if roi is not None else None,
        "profit_per_recovered_order": (
            round(net_profit / recovered_orders, 2) if recovered_orders > 0 else None
        ),
    }
