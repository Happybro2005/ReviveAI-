"""Shared Pydantic schemas."""
from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ErrorDetail(BaseModel):
    error: str = Field(description="Machine-readable error code.")
    message: str = Field(description="Human-readable explanation.")
    detail: Any | None = None


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int


class MetaEnvelope(BaseModel):
    """Wraps any payload derived from the synthetic dataset with its disclosure."""

    data: Any
    disclosure: str


class HealthResponse(BaseModel):
    status: str
    database: str
    database_detail: str | None = None
    models_trained: list[str]
    models_missing: list[str]
    reviews_analysed: bool | None = None
    disclosure: str


class Contribution(BaseModel):
    feature: str
    label: str
    value: Any = None
    contribution: float
    direction: str
    percent_of_total: float


class RiskBand(BaseModel):
    level: str
    count: int
    share: float
