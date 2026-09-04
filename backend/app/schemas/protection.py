"""Schemas for the PROTECT pillar."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

PaymentMethod = Literal["UPI", "CARD", "NETBANKING", "WALLET", "COD"]


class ReturnRiskInput(BaseModel):
    order_value: float = Field(gt=0, le=10_000_000)
    product_price: float = Field(gt=0, le=10_000_000)
    quantity: int = Field(default=1, ge=1, le=500)
    weight_kg: float = Field(default=0.5, ge=0, le=500)
    category: str = Field(default="Apparel", max_length=64)
    payment_method: PaymentMethod = "UPI"
    is_cod: bool = False
    has_size_variants: bool = False
    prior_order_count: int = Field(default=0, ge=0, le=10_000)
    prior_return_count: int = Field(default=0, ge=0, le=10_000)
    prior_rto_count: int = Field(default=0, ge=0, le=10_000)
    # Review-derived product signals. Supplied by the caller, or looked up from
    # product_voc_signals when product_id is given.
    product_id: int | None = None
    voc_review_count: float = Field(default=0, ge=0)
    voc_avg_rating: float = Field(default=0, ge=0, le=5)
    voc_size_fit_rate: float = Field(default=0, ge=0, le=1)
    voc_quality_rate: float = Field(default=0, ge=0, le=1)
    voc_delivery_rate: float = Field(default=0, ge=0, le=1)
    voc_packaging_rate: float = Field(default=0, ge=0, le=1)
    customer_id: int | None = None


class RTORiskInput(BaseModel):
    order_value: float = Field(gt=0, le=10_000_000)
    product_price: float = Field(default=0, ge=0, le=10_000_000)
    quantity: int = Field(default=1, ge=1, le=500)
    weight_kg: float = Field(default=0.5, ge=0, le=500)
    category: str = Field(default="Apparel", max_length=64)
    payment_method: PaymentMethod = "COD"
    is_cod: bool | None = None
    courier: str = Field(default="Delhivery", max_length=48)
    city: str = Field(default="Mumbai", max_length=80)
    promised_days: int = Field(default=4, ge=1, le=60)
    prior_order_count: int = Field(default=0, ge=0, le=10_000)
    prior_rto_count: int = Field(default=0, ge=0, le=10_000)
    prior_return_count: int = Field(default=0, ge=0, le=10_000)
    prior_delivery_failures: int = Field(default=0, ge=0, le=10_000)
    customer_id: int | None = None


class RiskFactor(BaseModel):
    feature: str
    label: str
    value: Any = None
    contribution: float
    direction: str
    percent_of_total: float


class ReturnRiskResponse(BaseModel):
    return_probability: float
    risk_level: str
    top_factors: list[RiskFactor]
    recommended_action: str
    model_version: str
    model_algorithm: str | None = None
    voc_context: dict[str, Any] | None = None
    disclosure: str


class RTORiskResponse(BaseModel):
    rto_probability: float
    risk_level: str
    top_factors: list[RiskFactor]
    recommended_action: str
    model_version: str
    model_algorithm: str | None = None
    policy_note: str
    disclosure: str


class AnomalyInput(BaseModel):
    customer_id: int | None = None
    order_count: int = Field(default=0, ge=0, le=100_000)
    total_spend: float = Field(default=0, ge=0)
    return_count: int = Field(default=0, ge=0, le=100_000)
    rto_count: int = Field(default=0, ge=0, le=100_000)
    shipment_count: int = Field(default=0, ge=0, le=100_000)
    cod_refusal_count: int = Field(default=0, ge=0, le=100_000)
    delivery_failure_count: int = Field(default=0, ge=0, le=100_000)
    orders_per_active_day: float = Field(default=0, ge=0)
    avg_order_value: float = Field(default=0, ge=0)
    return_rate: float = Field(default=0, ge=0, le=1)
    rto_rate: float = Field(default=0, ge=0, le=1)
    cod_share: float = Field(default=0, ge=0, le=1)
    declared_weight_kg: float = Field(default=0, ge=0)
    measured_weight_kg: float = Field(default=0, ge=0)


class AnomalyResponse(BaseModel):
    anomaly_score: float
    risk_level: str
    anomaly_class: str
    triggered_rules: list[dict[str, Any]]
    evidence: list[str]
    recommended_action: str
    model_score: float | None
    model_version: str
    note: str
    disclosure: str


class ProtectionDecisionInput(BaseModel):
    order_value: float = Field(gt=0, le=10_000_000)
    is_cod: bool = False
    rto_probability: float = Field(ge=0, le=1)
    return_probability: float = Field(ge=0, le=1)
    voc_signals: list[str] = []
