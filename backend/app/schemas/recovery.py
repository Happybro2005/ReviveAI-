"""Schemas for the RECOVER pillar."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

DeviceType = Literal["MOBILE", "DESKTOP", "TABLET"]
PaymentMethod = Literal["UPI", "CARD", "NETBANKING", "WALLET", "COD"]
CheckoutStage = Literal["CART", "ADDRESS", "SHIPPING", "PAYMENT", "REVIEW"]


class CheckoutSessionInput(BaseModel):
    """A checkout to score. Only pre-outcome signals are accepted."""

    cart_value: float = Field(gt=0, le=10_000_000, description="Cart value in INR.")
    shipping_cost: float = Field(default=0, ge=0, le=1_000_000)
    item_count: int = Field(default=1, ge=1, le=500)
    payment_attempts: int = Field(default=0, ge=0, le=50)
    payment_failed: bool = False
    payment_method: PaymentMethod = "UPI"
    device_type: DeviceType = "MOBILE"
    checkout_stage: CheckoutStage = "PAYMENT"
    session_duration_sec: int = Field(default=0, ge=0, le=86_400)
    coupon_applied: bool = False
    coupon_failed: bool = False
    address_edits: int = Field(default=0, ge=0, le=50)
    page_errors: int = Field(default=0, ge=0, le=100)
    hour_of_day: int = Field(default=12, ge=0, le=23)
    is_weekend: bool = False
    prior_order_count: int = Field(default=0, ge=0, le=10_000)
    prior_abandonment_count: int = Field(default=0, ge=0, le=10_000)
    prior_return_count: int = Field(default=0, ge=0, le=10_000)
    prior_rto_count: int = Field(default=0, ge=0, le=10_000)
    customer_id: int | None = None

    @model_validator(mode="after")
    def check_shipping(self) -> "CheckoutSessionInput":
        if self.shipping_cost > self.cart_value * 5:
            raise ValueError("shipping_cost is implausibly large relative to cart_value")
        if self.coupon_failed and not self.coupon_applied:
            # A coupon cannot fail if none was applied; treat as applied.
            object.__setattr__(self, "coupon_applied", True)
        return self

    @property
    def shipping_cart_ratio(self) -> float:
        return self.shipping_cost / self.cart_value if self.cart_value else 0.0


class Evidence(BaseModel):
    code: str
    description: str
    observed: str
    weight: float


class ReasonDiagnosis(BaseModel):
    primary_reason: str
    label: str
    confidence: float
    evidence: list[Evidence]
    alternatives: list[dict[str, Any]] = []


class AbandonmentPrediction(BaseModel):
    abandonment_probability: float
    risk_level: str
    model_version: str
    model_algorithm: str | None = None
    explanation: list[dict[str, Any]] = []


class RecoveryPredictionResponse(BaseModel):
    abandonment: AbandonmentPrediction
    reason: ReasonDiagnosis
    recovery_probability_baseline: float
    recovery_probability_best_action: float
    disclosure: str


class ActionEconomics(BaseModel):
    action: str
    label: str
    channel: str
    probability: float
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
    breakdown: dict[str, Any] = {}


class DecisionResponse(BaseModel):
    pillar: str
    next_best_action: ActionEconomics
    alternatives: list[ActionEconomics]
    rationale: str
    inputs: dict[str, Any]
    disclosures: list[str]


class InterventionCreate(BaseModel):
    abandoned_cart_id: int | None = None
    order_id: int | None = None
    customer_id: int
    pillar: Literal["RECOVERY", "PROTECTION"] = "RECOVERY"
    action: str = Field(min_length=1, max_length=40)
    channel: str = Field(default="EMAIL", max_length=24)
    predicted_probability: float = Field(ge=0, le=1)
    expected_revenue: float = Field(default=0, ge=0)
    intervention_cost: float = Field(default=0, ge=0)
    discount_cost: float = Field(default=0, ge=0)
    expected_profit: float = 0
    model_version: str | None = None


class InterventionResponse(BaseModel):
    id: int
    customer_id: int
    pillar: str
    action: str
    channel: str
    sent_at: str
    predicted_probability: float
    expected_profit: float
    outcome: str
