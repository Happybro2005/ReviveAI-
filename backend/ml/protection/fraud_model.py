"""Hybrid anomaly detection: deterministic business rules + IsolationForest.

Two things are kept strictly apart, because conflating them is how legitimate
customers get punished for a courier's mistake:

  CUSTOMER_BEHAVIOR      patterns in what a customer does (serial returns,
                         repeated COD refusal, unusual order velocity)
  LOGISTICS_OPERATIONAL  patterns in how a shipment was handled (weight
                         mismatch, repeated failed delivery attempts on a lane)

Nothing here is called "fraud" on its own. A rule hit is evidence; the
IsolationForest score is a second opinion; the output is a risk level and a
recommended *review* step. The final judgement stays with a human.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..common import ModelStore

MODEL_NAME = "anomaly"

CUSTOMER_BEHAVIOR = "CUSTOMER_BEHAVIOR"
LOGISTICS_OPERATIONAL = "LOGISTICS_OPERATIONAL"


@dataclass
class Rule:
    code: str
    description: str
    anomaly_class: str
    weight: float
    action: str


RULES: dict[str, Rule] = {
    "RETURN_RATE_HIGH": Rule(
        "RETURN_RATE_HIGH",
        "Return rate above 60% across 4 or more orders.",
        CUSTOMER_BEHAVIOR, 0.30, "MANUAL_REVIEW",
    ),
    "RTO_RATE_HIGH": Rule(
        "RTO_RATE_HIGH",
        "More than half of this customer's shipments came back undelivered.",
        CUSTOMER_BEHAVIOR, 0.30, "PAYMENT_CONFIRMATION",
    ),
    "COD_REFUSAL_PATTERN": Rule(
        "COD_REFUSAL_PATTERN",
        "Repeated refusal of cash-on-delivery shipments.",
        CUSTOMER_BEHAVIOR, 0.25, "PAYMENT_CONFIRMATION",
    ),
    "ORDER_VELOCITY": Rule(
        "ORDER_VELOCITY",
        "Order rate far above this customer's own historical pace.",
        CUSTOMER_BEHAVIOR, 0.20, "ORDER_CONFIRMATION",
    ),
    "WEIGHT_MISMATCH": Rule(
        "WEIGHT_MISMATCH",
        "Measured shipment weight differs materially from the declared weight.",
        LOGISTICS_OPERATIONAL, 0.30, "LOGISTICS_REVIEW",
    ),
    "REPEATED_DELIVERY_FAILURE": Rule(
        "REPEATED_DELIVERY_FAILURE",
        "Multiple failed delivery attempts recorded.",
        LOGISTICS_OPERATIONAL, 0.25, "LOGISTICS_REVIEW",
    ),
}


@dataclass
class AnomalyResult:
    anomaly_score: float
    risk_level: str
    anomaly_class: str
    triggered_rules: list[dict[str, Any]] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    recommended_action: str = "NO_ACTION"
    model_score: float | None = None
    model_version: str = "rules-only"

    def to_dict(self) -> dict[str, Any]:
        return {
            "anomaly_score": round(self.anomaly_score, 4),
            "risk_level": self.risk_level,
            "anomaly_class": self.anomaly_class,
            "triggered_rules": self.triggered_rules,
            "evidence": self.evidence,
            "recommended_action": self.recommended_action,
            "model_score": (
                round(self.model_score, 4) if self.model_score is not None else None
            ),
            "model_version": self.model_version,
            "note": (
                "An anomaly is a prompt to review, not a fraud determination. "
                "Operational anomalies are reported separately from customer behaviour."
            ),
        }


def _rule_pass(payload: dict[str, Any]) -> tuple[list[Rule], list[str]]:
    fired: list[Rule] = []
    evidence: list[str] = []

    orders = float(payload.get("order_count") or 0)
    returns = float(payload.get("return_count") or 0)
    rto = float(payload.get("rto_count") or 0)
    shipments = float(payload.get("shipment_count") or orders)
    cod_refusals = float(payload.get("cod_refusal_count") or 0)
    delivery_failures = float(payload.get("delivery_failure_count") or 0)
    velocity = float(payload.get("orders_per_active_day") or 0)
    declared = float(payload.get("declared_weight_kg") or 0)
    measured = float(payload.get("measured_weight_kg") or 0)

    if orders >= 4 and returns / orders > 0.60:
        fired.append(RULES["RETURN_RATE_HIGH"])
        evidence.append(f"{int(returns)} returns across {int(orders)} orders "
                        f"({returns / orders * 100:.0f}%)")
    if shipments >= 4 and rto / shipments > 0.50:
        fired.append(RULES["RTO_RATE_HIGH"])
        evidence.append(f"{int(rto)} RTOs across {int(shipments)} shipments "
                        f"({rto / shipments * 100:.0f}%)")
    if cod_refusals >= 2:
        fired.append(RULES["COD_REFUSAL_PATTERN"])
        evidence.append(f"{int(cod_refusals)} cash-on-delivery refusals")
    if velocity > 1.5 and orders >= 5:
        fired.append(RULES["ORDER_VELOCITY"])
        evidence.append(f"{velocity:.2f} orders per active day")
    if declared > 0 and abs(measured - declared) / declared > 0.50:
        fired.append(RULES["WEIGHT_MISMATCH"])
        evidence.append(f"declared {declared:.2f}kg vs measured {measured:.2f}kg")
    if delivery_failures >= 3:
        fired.append(RULES["REPEATED_DELIVERY_FAILURE"])
        evidence.append(f"{int(delivery_failures)} failed delivery attempts")

    return fired, evidence


def analyze(
    payload: dict[str, Any],
    store: ModelStore | None = None,
) -> AnomalyResult:
    """Score one customer/shipment against rules and the trained detector."""
    fired, evidence = _rule_pass(payload)
    rule_score = min(1.0, sum(r.weight for r in fired))

    model_score: float | None = None
    version = "rules-only"
    if store is not None and store.available(MODEL_NAME):
        try:
            import pandas as pd

            pipeline, meta = store.require(MODEL_NAME)
            row = pd.DataFrame(
                [{f: float(payload.get(f) or 0.0) for f in meta.feature_names}],
                columns=meta.feature_names,
            )
            # decision_function: negative is more anomalous. Map to 0..1.
            raw = float(pipeline.decision_function(row)[0])
            model_score = max(0.0, min(1.0, 0.5 - raw))
            version = meta.version
        except Exception:
            model_score = None

    if model_score is None:
        score = rule_score
    else:
        # Rules dominate (they are explainable and precise); the detector adds
        # sensitivity to patterns no rule anticipated.
        score = min(1.0, 0.65 * rule_score + 0.35 * model_score)

    if score >= 0.60:
        level = "HIGH"
    elif score >= 0.30:
        level = "MEDIUM"
    else:
        level = "LOW"

    customer_rules = [r for r in fired if r.anomaly_class == CUSTOMER_BEHAVIOR]
    logistics_rules = [r for r in fired if r.anomaly_class == LOGISTICS_OPERATIONAL]
    if customer_rules and not logistics_rules:
        anomaly_class = CUSTOMER_BEHAVIOR
    elif logistics_rules and not customer_rules:
        anomaly_class = LOGISTICS_OPERATIONAL
    elif fired:
        anomaly_class = "MIXED"
    else:
        anomaly_class = "UNCLASSIFIED"

    if fired:
        action = max(fired, key=lambda r: r.weight).action
    elif level == "HIGH":
        action = "MANUAL_REVIEW"
    else:
        action = "NO_ACTION"

    return AnomalyResult(
        anomaly_score=score,
        risk_level=level,
        anomaly_class=anomaly_class,
        triggered_rules=[
            {
                "code": r.code,
                "description": r.description,
                "anomaly_class": r.anomaly_class,
                "weight": r.weight,
            }
            for r in fired
        ],
        evidence=evidence or ["No rule thresholds exceeded."],
        recommended_action=action,
        model_score=model_score,
        model_version=version,
    )
