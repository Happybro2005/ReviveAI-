"""Schemas for the LISTEN pillar (Voice of Customer)."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator

MAX_REVIEW_CHARS = 8000


class ReviewAnalyzeRequest(BaseModel):
    review_text: str = Field(min_length=1, max_length=MAX_REVIEW_CHARS)
    rating: int | None = Field(default=None, ge=1, le=5)
    product_id: int | None = None
    persist: bool = Field(
        default=False,
        description="Store the review and its analysis in the database.",
    )
    customer_id: int | None = None

    @field_validator("review_text")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("review_text cannot be blank or whitespace only")
        return v


class ClauseSentiment(BaseModel):
    text: str
    score: float
    label: str


class AspectResult(BaseModel):
    aspect: str
    sentiment: str
    sentiment_score: float
    evidence_span: str
    mentions: int
    risk_signal: str | None = None


class SuggestionResult(BaseModel):
    aspect: str
    suggestion_text: str
    normalized_suggestion: str
    source_span: str


class ReviewAnalysisResponse(BaseModel):
    text: str
    language: str
    sentiment: str
    sentiment_score: float
    confidence: float
    lexicon_score: float
    model_label: str | None = None
    model_confidence: float | None = None
    model_version: str
    clauses: list[ClauseSentiment] = []
    aspects: list[AspectResult] = []
    suggestions: list[SuggestionResult] = []
    topics: list[str] = []
    priority: str
    business_impact: str
    risk_signals: list[str] = []
    recommended_action: str
    recommended_action_detail: str
    review_id: int | None = None
    disclosure: str


class BulkAnalyzeSummary(BaseModel):
    rows_received: int
    rows_processed: int
    rows_skipped: int
    duplicates_skipped: int
    persisted: int
    errors: list[str] = []
    sentiment_distribution: dict[str, int] = {}
    average_rating: float | None = None
    top_issues: list[dict[str, Any]] = []
    top_suggestions: list[dict[str, Any]] = []
    aspect_analysis: list[dict[str, Any]] = []
    seller_recommendations: list[dict[str, Any]] = []
    disclosure: str


class AspectBreakdown(BaseModel):
    aspect: str
    aspect_label: str
    total: int
    positive: int
    negative: int
    neutral: int
    positive_share: float
    negative_share: float
    risk_signal: str | None = None


class TopicFrequency(BaseModel):
    aspect: str
    aspect_label: str
    negative_mentions: int
    share_of_reviews: float
    risk_signal: str | None = None


class VocInsightsResponse(BaseModel):
    total_reviews: int
    analysed_reviews: int
    average_rating: float | None
    sentiment_distribution: dict[str, int]
    aspect_analysis: list[AspectBreakdown]
    top_concerns: list[TopicFrequency]
    top_suggestions: list[dict[str, Any]]
    disclosure: str


class SellerRecommendationOut(BaseModel):
    id: int | None = None
    scope: str
    aspect: str
    aspect_label: str | None = None
    problem: str
    recommendation: str
    priority: str
    supporting_review_count: int
    negative_share: float
    evidence: dict[str, Any] | None = None
    estimated_business_impact: float
    impact_basis: str | None = None
    linked_risk_signal: str | None = None
    category: str | None = None
    product_id: int | None = None
    product_title: str | None = None
    affected: str | None = None
