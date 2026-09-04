"""SQLAlchemy models for ReviveAI.

Importing this package registers every table on `Base.metadata`, which is what
Alembic autogenerate and `Base.metadata.create_all` rely on.
"""
from .base import Base, TimestampMixin, utcnow
from .core import Customer, Order, OrderItem, Payment, Product
from .protection import (
    FraudEvent,
    LogisticsEvent,
    Return,
    ReturnRiskScore,
    RTORiskScore,
    Shipment,
)
from .recovery import AbandonedCart, CheckoutSession, Conversion, Intervention
from .registry import ModelRegistry
from .voc import (
    CustomerSuggestion,
    ProductVocSignal,
    Review,
    ReviewAnalysis,
    ReviewAspect,
    SellerRecommendation,
)

__all__ = [
    "Base",
    "TimestampMixin",
    "utcnow",
    # core
    "Customer",
    "Product",
    "Order",
    "OrderItem",
    "Payment",
    # recovery
    "CheckoutSession",
    "AbandonedCart",
    "Intervention",
    "Conversion",
    # protection
    "Shipment",
    "LogisticsEvent",
    "Return",
    "ReturnRiskScore",
    "RTORiskScore",
    "FraudEvent",
    # voc
    "Review",
    "ReviewAnalysis",
    "ReviewAspect",
    "CustomerSuggestion",
    "SellerRecommendation",
    "ProductVocSignal",
    # registry
    "ModelRegistry",
]
