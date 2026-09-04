"""Pillar 1 (RECOVER): checkout sessions, abandoned carts, interventions, conversions.

Leakage note
------------
`CheckoutSession` deliberately separates *pre-outcome* behavioural columns from
the outcome column `abandoned`. The abandonment model may read only the
pre-outcome columns. Everything describing what happened *after* abandonment
lives on `AbandonedCart`, `Intervention` and `Conversion`, and is never fed back
into the abandonment feature set. See `ml/recovery/features.py`.
"""
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


class CheckoutSession(Base, TimestampMixin):
    __tablename__ = "checkout_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_ref: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"), index=True
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

    # ---- Pre-outcome features (safe for the abandonment model) --------------
    cart_value: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    item_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    shipping_cost: Mapped[float] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    shipping_cart_ratio: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    payment_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    payment_failed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    payment_method: Mapped[str] = mapped_column(String(24), index=True)
    device_type: Mapped[str] = mapped_column(String(16), index=True)
    session_duration_sec: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    checkout_stage: Mapped[str] = mapped_column(String(24), index=True)
    coupon_applied: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    coupon_failed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    address_edits: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    page_errors: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    hour_of_day: Mapped[int] = mapped_column(Integer, default=12, nullable=False)
    is_weekend: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Point-in-time customer history snapshot, computed at session time.
    prior_order_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    prior_abandonment_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    prior_return_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    prior_rto_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # ---- Outcome (target only; never an input feature) ----------------------
    abandoned: Mapped[bool] = mapped_column(Boolean, nullable=False, index=True)

    customer: Mapped["Customer"] = relationship()  # noqa: F821
    abandoned_cart: Mapped["AbandonedCart | None"] = relationship(
        back_populates="session", uselist=False
    )

    __table_args__ = (
        CheckConstraint("cart_value >= 0", name="ck_session_cart_value_nonneg"),
        CheckConstraint("payment_attempts >= 0", name="ck_session_attempts_nonneg"),
        CheckConstraint(
            "shipping_cart_ratio >= 0", name="ck_session_ship_ratio_nonneg"
        ),
        Index("ix_sessions_customer_started", "customer_id", "started_at"),
        Index("ix_sessions_abandoned_started", "abandoned", "started_at"),
    )


class AbandonedCart(Base, TimestampMixin):
    """One row per abandoned checkout session, carrying diagnosis + outcome."""

    __tablename__ = "abandoned_carts"

    id: Mapped[int] = mapped_column(primary_key=True)
    checkout_session_id: Mapped[int] = mapped_column(
        ForeignKey("checkout_sessions.id", ondelete="CASCADE"), unique=True, index=True
    )
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"), index=True
    )
    abandoned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    cart_value: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)

    # Diagnosed by the reason engine from behavioural evidence.
    primary_reason: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    reason_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    reason_evidence: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ---- Post-intervention outcome (target for the recovery model) ----------
    recovered: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    recovered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    recovered_revenue: Mapped[float] = mapped_column(Numeric(12, 2), default=0, nullable=False)

    session: Mapped["CheckoutSession"] = relationship(back_populates="abandoned_cart")
    interventions: Mapped[list["Intervention"]] = relationship(
        back_populates="cart", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_carts_reason_recovered", "primary_reason", "recovered"),
    )


class Intervention(Base, TimestampMixin):
    """A recovery or protection action actually dispatched for a cart/order."""

    __tablename__ = "interventions"

    id: Mapped[int] = mapped_column(primary_key=True)
    abandoned_cart_id: Mapped[int | None] = mapped_column(
        ForeignKey("abandoned_carts.id", ondelete="CASCADE"), nullable=True, index=True
    )
    order_id: Mapped[int | None] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), nullable=True, index=True
    )
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"), index=True
    )
    pillar: Mapped[str] = mapped_column(String(16), index=True)  # RECOVERY / PROTECTION
    action: Mapped[str] = mapped_column(String(40), index=True)
    channel: Mapped[str] = mapped_column(String(24))
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

    # Economics recorded at decision time so outcomes can be audited later.
    predicted_probability: Mapped[float] = mapped_column(Float, nullable=False)
    expected_revenue: Mapped[float] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    intervention_cost: Mapped[float] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    discount_cost: Mapped[float] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    expected_profit: Mapped[float] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    model_version: Mapped[str | None] = mapped_column(String(64), nullable=True)

    outcome: Mapped[str] = mapped_column(String(16), default="PENDING", index=True)

    cart: Mapped["AbandonedCart | None"] = relationship(back_populates="interventions")
    conversion: Mapped["Conversion | None"] = relationship(
        back_populates="intervention", uselist=False
    )

    __table_args__ = (
        CheckConstraint(
            "predicted_probability >= 0 AND predicted_probability <= 1",
            name="ck_intervention_prob_range",
        ),
        Index("ix_interventions_pillar_action", "pillar", "action"),
    )


class Conversion(Base, TimestampMixin):
    """Realised outcome of an intervention."""

    __tablename__ = "conversions"

    id: Mapped[int] = mapped_column(primary_key=True)
    intervention_id: Mapped[int] = mapped_column(
        ForeignKey("interventions.id", ondelete="CASCADE"), unique=True, index=True
    )
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"), index=True
    )
    order_id: Mapped[int | None] = mapped_column(
        ForeignKey("orders.id", ondelete="SET NULL"), nullable=True, index=True
    )
    converted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    revenue: Mapped[float] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    realised_cost: Mapped[float] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    realised_profit: Mapped[float] = mapped_column(Numeric(12, 2), default=0, nullable=False)

    intervention: Mapped["Intervention"] = relationship(back_populates="conversion")
