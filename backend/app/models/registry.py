"""Model registry: which model version is live and how it scored."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class ModelRegistry(Base, TimestampMixin):
    __tablename__ = "model_registry"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(48), index=True)
    version: Mapped[str] = mapped_column(String(64), index=True)
    algorithm: Mapped[str] = mapped_column(String(64))
    trained_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    artifact_path: Mapped[str] = mapped_column(String(400))
    feature_names: Mapped[str] = mapped_column(Text)  # JSON list
    metrics: Mapped[str] = mapped_column(Text)  # JSON dict
    training_rows: Mapped[str | None] = mapped_column(String(32), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (Index("ix_registry_name_trained", "name", "trained_at"),)
