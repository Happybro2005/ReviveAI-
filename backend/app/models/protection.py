"""Pillar 2 (PROTECT): returns, RTO, shipments, logistics events, anomalies."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin


class Shipment(Base, TimestampMixin):
    __tablename__ = "shipments"

    id: Mapped[int] = mapped_column(primary_key=True)
    awb: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), index=True
    )
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"), index=True
    )
    courier: Mapped[str] = mapped_column(String(48), index=True)
    shipped_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    delivered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    promised_days: Mapped[int] = mapped_column(Integer, default=4, nullable=False)
    actual_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    delivery_attempts: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    declared_weight_kg: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    measured_weight_kg: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    status: Mapped[str] = mapped_column(String(24), index=True)  # DELIVERED / RTO / IN_TRANSIT
    is_rto: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    rto_reason: Mapped[str | None] = mapped_column(String(48), nullable=True, index=True)

    events: Mapped[list["LogisticsEvent"]] = relationship(
        back_populates="shipment", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint("delivery_attempts >= 0", name="ck_shipment_attempts_nonneg"),
        Index("ix_shipments_courier_status", "courier", "status"),
    )

    @property
    def weight_mismatch_ratio(self) -> float:
        if not self.declared_weight_kg:
            return 0.0
        return abs(self.measured_weight_kg - self.declared_weight_kg) / self.declared_weight_kg

    @property
    def is_delayed(self) -> bool:
        return self.actual_days is not None and self.actual_days > self.promised_days


class LogisticsEvent(Base, TimestampMixin):
    __tablename__ = "logistics_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    shipment_id: Mapped[int] = mapped_column(
        ForeignKey("shipments.id", ondelete="CASCADE"), index=True
    )
    event_type: Mapped[str] = mapped_column(String(40), index=True)
    event_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    location: Mapped[str | None] = mapped_column(String(80), nullable=True)
    detail: Mapped[str | None] = mapped_column(String(240), nullable=True)

    shipment: Mapped["Shipment"] = relationship(back_populates="events")

    __table_args__ = (Index("ix_events_shipment_type", "shipment_id", "event_type"),)


class Return(Base, TimestampMixin):
    __tablename__ = "returns"

    id: Mapped[int] = mapped_column(primary_key=True)
    return_ref: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), index=True
    )
    order_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("order_items.id", ondelete="SET NULL"), nullable=True, index=True
    )
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"), index=True
    )
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT"), index=True
    )
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    reason: Mapped[str] = mapped_column(String(40), index=True)
    refund_amount: Mapped[float] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="REQUESTED", index=True)

    __table_args__ = (
        CheckConstraint("refund_amount >= 0", name="ck_return_refund_nonneg"),
        Index("ix_returns_product_reason", "product_id", "reason"),
    )


class ReturnRiskScore(Base, TimestampMixin):
    """Scored return risk for an order, with the explanation that produced it."""

    __tablename__ = "return_risk_scores"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int | None] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), nullable=True, index=True
    )
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"), index=True
    )
    product_id: Mapped[int | None] = mapped_column(
        ForeignKey("products.id", ondelete="SET NULL"), nullable=True, index=True
    )
    scored_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    return_probability: Mapped[float] = mapped_column(Float, nullable=False)
    risk_level: Mapped[str] = mapped_column(String(12), index=True)
    top_factors: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON string
    recommended_action: Mapped[str | None] = mapped_column(String(40), nullable=True)
    model_version: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "return_probability >= 0 AND return_probability <= 1",
            name="ck_return_score_range",
        ),
    )


class RTORiskScore(Base, TimestampMixin):
    __tablename__ = "rto_risk_scores"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int | None] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), nullable=True, index=True
    )
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"), index=True
    )
    scored_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    rto_probability: Mapped[float] = mapped_column(Float, nullable=False)
    risk_level: Mapped[str] = mapped_column(String(12), index=True)
    top_factors: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON string
    recommended_action: Mapped[str | None] = mapped_column(String(40), nullable=True)
    model_version: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "rto_probability >= 0 AND rto_probability <= 1", name="ck_rto_score_range"
        ),
    )


class FraudEvent(Base, TimestampMixin):
    """An anomaly detected by the hybrid rules + IsolationForest engine.

    `anomaly_class` separates CUSTOMER_BEHAVIOR from LOGISTICS_OPERATIONAL so the
    UI never labels an operational outlier as customer fraud.
    """

    __tablename__ = "fraud_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int | None] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"), nullable=True, index=True
    )
    order_id: Mapped[int | None] = mapped_column(
        ForeignKey("orders.id", ondelete="SET NULL"), nullable=True, index=True
    )
    shipment_id: Mapped[int | None] = mapped_column(
        ForeignKey("shipments.id", ondelete="SET NULL"), nullable=True, index=True
    )
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    anomaly_class: Mapped[str] = mapped_column(String(32), index=True)
    anomaly_score: Mapped[float] = mapped_column(Float, nullable=False)
    risk_level: Mapped[str] = mapped_column(String(12), index=True)
    triggered_rules: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON string
    evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommended_action: Mapped[str | None] = mapped_column(String(40), nullable=True)
    estimated_exposure: Mapped[float] = mapped_column(
        Numeric(12, 2), default=0, nullable=False
    )
    model_version: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        Index("ix_fraud_class_level", "anomaly_class", "risk_level"),
    )
