"""Core commerce entities: customers, products, orders, payments."""
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
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin


class Customer(Base, TimestampMixin):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(primary_key=True)
    external_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(200), index=True)
    city: Mapped[str] = mapped_column(String(80), index=True)
    state: Mapped[str] = mapped_column(String(80))
    pincode: Mapped[str] = mapped_column(String(12), index=True)
    signup_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

    # Rolling behavioural aggregates, current as of the last seed/refresh.
    # Feature builders that train models snapshot history point-in-time instead
    # of reading these, so that future behaviour never leaks into training data.
    order_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_spend: Mapped[float] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    return_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rto_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    abandonment_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    delivery_failure_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cod_refusal_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    segment: Mapped[str] = mapped_column(String(24), default="NEW", index=True)

    orders: Mapped[list["Order"]] = relationship(back_populates="customer")
    payments: Mapped[list["Payment"]] = relationship(back_populates="customer")

    __table_args__ = (
        CheckConstraint("order_count >= 0", name="ck_customer_order_count_nonneg"),
        CheckConstraint("return_count >= 0", name="ck_customer_return_count_nonneg"),
        Index("ix_customers_segment_city", "segment", "city"),
    )

    @property
    def return_rate(self) -> float:
        return (self.return_count / self.order_count) if self.order_count else 0.0

    @property
    def rto_rate(self) -> float:
        return (self.rto_count / self.order_count) if self.order_count else 0.0


class Product(Base, TimestampMixin):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    sku: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(240))
    category: Mapped[str] = mapped_column(String(64), index=True)
    subcategory: Mapped[str] = mapped_column(String(64), index=True)
    price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    cost_price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    weight_kg: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    has_size_variants: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Maintained from actual review rows by the seeder and the review pipeline.
    avg_rating: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    review_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    __table_args__ = (
        CheckConstraint("price > 0", name="ck_product_price_positive"),
        CheckConstraint(
            "avg_rating >= 0 AND avg_rating <= 5", name="ck_product_rating_range"
        ),
        Index("ix_products_category_price", "category", "price"),
    )

    @property
    def gross_margin(self) -> float:
        price = float(self.price)
        return (price - float(self.cost_price)) / price if price else 0.0


class Order(Base, TimestampMixin):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_ref: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"), index=True
    )
    checkout_session_id: Mapped[int | None] = mapped_column(
        ForeignKey("checkout_sessions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    order_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    order_value: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    shipping_cost: Mapped[float] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    discount_amount: Mapped[float] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    payment_method: Mapped[str] = mapped_column(String(24), index=True)
    is_cod: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(24), default="PLACED", index=True)

    customer: Mapped["Customer"] = relationship(back_populates="orders")
    items: Mapped[list["OrderItem"]] = relationship(
        back_populates="order", cascade="all, delete-orphan"
    )
    payments: Mapped[list["Payment"]] = relationship(back_populates="order")

    __table_args__ = (
        CheckConstraint("order_value >= 0", name="ck_order_value_nonneg"),
        Index("ix_orders_customer_date", "customer_id", "order_date"),
    )


class OrderItem(Base, TimestampMixin):
    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), index=True
    )
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT"), index=True
    )
    quantity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    unit_price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    selected_size: Mapped[str | None] = mapped_column(String(16), nullable=True)

    order: Mapped["Order"] = relationship(back_populates="items")
    product: Mapped["Product"] = relationship()

    __table_args__ = (CheckConstraint("quantity > 0", name="ck_order_item_qty_positive"),)


class Payment(Base, TimestampMixin):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    payment_ref: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    order_id: Mapped[int | None] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), nullable=True, index=True
    )
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"), index=True
    )
    checkout_session_id: Mapped[int | None] = mapped_column(
        ForeignKey("checkout_sessions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    method: Mapped[str] = mapped_column(String(24), index=True)
    status: Mapped[str] = mapped_column(String(24), index=True)  # SUCCESS / FAILED / PENDING
    failure_reason: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    attempt_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    attempted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

    order: Mapped["Order | None"] = relationship(back_populates="payments")
    customer: Mapped["Customer"] = relationship(back_populates="payments")

    __table_args__ = (
        CheckConstraint("amount >= 0", name="ck_payment_amount_nonneg"),
        Index("ix_payments_status_method", "status", "method"),
    )
