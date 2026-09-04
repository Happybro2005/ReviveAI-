"""Pillar 3 (LISTEN): reviews and the derived intelligence layer."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin


class Review(Base, TimestampMixin):
    __tablename__ = "reviews"

    id: Mapped[int] = mapped_column(primary_key=True)
    review_ref: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    customer_id: Mapped[int | None] = mapped_column(
        ForeignKey("customers.id", ondelete="SET NULL"), nullable=True, index=True
    )
    product_id: Mapped[int | None] = mapped_column(
        ForeignKey("products.id", ondelete="SET NULL"), nullable=True, index=True
    )
    order_id: Mapped[int | None] = mapped_column(
        ForeignKey("orders.id", ondelete="SET NULL"), nullable=True, index=True
    )
    rating: Mapped[int] = mapped_column(Integer, index=True)
    review_text: Mapped[str] = mapped_column(Text)
    review_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    source: Mapped[str] = mapped_column(String(24), default="SEED", index=True)

    analysis: Mapped["ReviewAnalysis | None"] = relationship(
        back_populates="review", uselist=False, cascade="all, delete-orphan"
    )
    aspects: Mapped[list["ReviewAspect"]] = relationship(
        back_populates="review", cascade="all, delete-orphan"
    )
    suggestions: Mapped[list["CustomerSuggestion"]] = relationship(
        back_populates="review", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint("rating >= 1 AND rating <= 5", name="ck_review_rating_range"),
        Index("ix_reviews_product_date", "product_id", "review_date"),
    )


class ReviewAnalysis(Base, TimestampMixin):
    """Output of the NLP pipeline for one review."""

    __tablename__ = "review_analysis"

    id: Mapped[int] = mapped_column(primary_key=True)
    review_id: Mapped[int] = mapped_column(
        ForeignKey("reviews.id", ondelete="CASCADE"), unique=True, index=True
    )
    language: Mapped[str] = mapped_column(String(8), default="en", index=True)
    sentiment: Mapped[str] = mapped_column(String(12), index=True)  # POSITIVE/NEGATIVE/NEUTRAL/MIXED
    sentiment_score: Mapped[float] = mapped_column(Float, nullable=False)  # -1..1 polarity
    confidence: Mapped[float] = mapped_column(Float, nullable=False)  # 0..1
    priority: Mapped[str] = mapped_column(String(12), index=True)  # LOW/MEDIUM/HIGH/CRITICAL
    business_impact: Mapped[str | None] = mapped_column(Text, nullable=True)
    topics: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON string
    model_version: Mapped[str | None] = mapped_column(String(64), nullable=True)

    review: Mapped["Review"] = relationship(back_populates="analysis")

    __table_args__ = (
        CheckConstraint(
            "sentiment_score >= -1 AND sentiment_score <= 1", name="ck_analysis_score_range"
        ),
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1", name="ck_analysis_conf_range"
        ),
    )


class ReviewAspect(Base, TimestampMixin):
    """One (aspect, sentiment) pair extracted from a review, with its evidence span."""

    __tablename__ = "review_aspects"

    id: Mapped[int] = mapped_column(primary_key=True)
    review_id: Mapped[int] = mapped_column(
        ForeignKey("reviews.id", ondelete="CASCADE"), index=True
    )
    product_id: Mapped[int | None] = mapped_column(
        ForeignKey("products.id", ondelete="SET NULL"), nullable=True, index=True
    )
    aspect: Mapped[str] = mapped_column(String(32), index=True)
    sentiment: Mapped[str] = mapped_column(String(12), index=True)
    sentiment_score: Mapped[float] = mapped_column(Float, nullable=False)
    evidence_span: Mapped[str | None] = mapped_column(Text, nullable=True)

    review: Mapped["Review"] = relationship(back_populates="aspects")

    __table_args__ = (
        UniqueConstraint("review_id", "aspect", name="uq_review_aspect"),
        Index("ix_aspects_aspect_sentiment", "aspect", "sentiment"),
        Index("ix_aspects_product_aspect", "product_id", "aspect"),
    )


class CustomerSuggestion(Base, TimestampMixin):
    """An explicit improvement request detected in a review."""

    __tablename__ = "customer_suggestions"

    id: Mapped[int] = mapped_column(primary_key=True)
    review_id: Mapped[int] = mapped_column(
        ForeignKey("reviews.id", ondelete="CASCADE"), index=True
    )
    product_id: Mapped[int | None] = mapped_column(
        ForeignKey("products.id", ondelete="SET NULL"), nullable=True, index=True
    )
    aspect: Mapped[str] = mapped_column(String(32), index=True)
    suggestion_text: Mapped[str] = mapped_column(Text)
    normalized_suggestion: Mapped[str] = mapped_column(String(120), index=True)
    source_span: Mapped[str | None] = mapped_column(Text, nullable=True)

    review: Mapped["Review"] = relationship(back_populates="suggestions")

    __table_args__ = (
        Index("ix_suggestions_norm_aspect", "normalized_suggestion", "aspect"),
    )


class SellerRecommendation(Base, TimestampMixin):
    """Aggregated, evidence-backed business action derived from review data."""

    __tablename__ = "seller_recommendations"

    id: Mapped[int] = mapped_column(primary_key=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    scope: Mapped[str] = mapped_column(String(16), index=True)  # GLOBAL/CATEGORY/PRODUCT
    category: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    product_id: Mapped[int | None] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), nullable=True, index=True
    )
    aspect: Mapped[str] = mapped_column(String(32), index=True)
    problem: Mapped[str] = mapped_column(Text)
    recommendation: Mapped[str] = mapped_column(Text)
    priority: Mapped[str] = mapped_column(String(12), index=True)
    supporting_review_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    negative_share: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    evidence: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON string
    estimated_business_impact: Mapped[float] = mapped_column(
        Numeric(14, 2), default=0, nullable=False
    )
    impact_basis: Mapped[str | None] = mapped_column(Text, nullable=True)
    linked_risk_signal: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)

    __table_args__ = (
        Index("ix_recs_scope_priority", "scope", "priority"),
    )


class ProductVocSignal(Base, TimestampMixin):
    """Per-product review-derived signals consumed by the PROTECT models.

    This is the bridge that stops Voice of Customer from being an isolated
    dashboard: `size_fit_complaint_rate` feeds the return model,
    `delivery_complaint_rate` / `packaging_complaint_rate` feed the RTO and
    logistics risk views.
    """

    __tablename__ = "product_voc_signals"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), unique=True, index=True
    )
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    review_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    negative_share: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    size_fit_complaint_rate: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    quality_complaint_rate: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    delivery_complaint_rate: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    packaging_complaint_rate: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    support_complaint_rate: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    product: Mapped["Product"] = relationship()  # noqa: F821

    __table_args__ = (
        CheckConstraint(
            "size_fit_complaint_rate >= 0 AND size_fit_complaint_rate <= 1",
            name="ck_voc_sizefit_range",
        ),
    )
