"""End-to-end Voice-of-Customer pipeline for a single review.

    text -> clean -> language -> sentiment -> aspects -> aspect sentiment
         -> topics -> suggestions -> priority -> business impact -> action

Everything returned here is computed from the supplied text. Nothing is
templated onto the response.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .aspects import AspectResult, extract_aspects
from .lexicon import ASPECT_LABELS, ASPECT_RECOMMENDATION, ASPECT_RISK_SIGNAL
from .preprocess import clean_text
from .sentiment import MIXED, NEGATIVE, SentimentResult, analyze_sentiment
from .suggestions import SuggestionResult, extract_suggestions

PRIORITY_ORDER = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}

# Aspects whose failure costs money downstream (returns, RTO, lost checkouts)
# rather than only reputation.
_COST_BEARING = {"SIZE_FIT", "PRODUCT_QUALITY", "DELIVERY", "PACKAGING", "PAYMENT", "WEBSITE"}

_SIGNAL_LABELS = {
    "RETURN_RISK": "elevated return risk",
    "LOGISTICS_RISK": "logistics / RTO risk",
    "CHECKOUT_RISK": "checkout abandonment risk",
    "CX_RISK": "customer-experience risk",
}


@dataclass
class ReviewIntelligence:
    text: str
    language: str
    sentiment: SentimentResult
    aspects: list[AspectResult] = field(default_factory=list)
    suggestions: list[SuggestionResult] = field(default_factory=list)
    topics: list[str] = field(default_factory=list)
    priority: str = "LOW"
    business_impact: str = ""
    risk_signals: list[str] = field(default_factory=list)
    recommended_action: str = ""
    recommended_action_detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "language": self.language,
            **self.sentiment.to_dict(),
            "aspects": [a.to_dict() for a in self.aspects],
            "suggestions": [s.to_dict() for s in self.suggestions],
            "topics": self.topics,
            "priority": self.priority,
            "business_impact": self.business_impact,
            "risk_signals": self.risk_signals,
            "recommended_action": self.recommended_action,
            "recommended_action_detail": self.recommended_action_detail,
        }


def _priority(
    sentiment: SentimentResult,
    aspects: list[AspectResult],
    rating: int | None,
) -> str:
    negatives = [a for a in aspects if a.sentiment == NEGATIVE]
    cost_bearing = [a for a in negatives if a.aspect in _COST_BEARING]

    score = 0
    if sentiment.sentiment == NEGATIVE:
        score += 2
    elif sentiment.sentiment == MIXED:
        score += 1
    score += len(cost_bearing)
    if len(negatives) >= 3:
        score += 1
    if rating is not None:
        if rating <= 2:
            score += 2
        elif rating == 3:
            score += 1
    # A very strong negative signal on a cost-bearing aspect is escalated.
    if any(a.sentiment_score <= -0.6 for a in cost_bearing):
        score += 1

    if score >= 6:
        return "CRITICAL"
    if score >= 4:
        return "HIGH"
    if score >= 2:
        return "MEDIUM"
    return "LOW"


def _business_impact(aspects: list[AspectResult]) -> tuple[str, list[str]]:
    negatives = [a for a in aspects if a.sentiment == NEGATIVE]
    if not negatives:
        return ("No negative aspect detected; no revenue risk signal raised from "
                "this review.", [])
    signals: list[str] = []
    for a in negatives:
        sig = ASPECT_RISK_SIGNAL.get(a.aspect)
        if sig and sig not in signals:
            signals.append(sig)
    named = ", ".join(ASPECT_LABELS.get(a.aspect, a.aspect) for a in negatives)
    described = ", ".join(_SIGNAL_LABELS.get(s, s) for s in signals)
    return (
        f"Negative signal on {named}. This feeds {described} for the affected "
        f"product and customer.",
        signals,
    )


def analyze_review(
    text: str,
    rating: int | None = None,
    artifact_dir: Path | None = None,
) -> ReviewIntelligence:
    """Run the full pipeline over one review."""
    cleaned = clean_text(text)
    sentiment = analyze_sentiment(cleaned, artifact_dir=artifact_dir)
    aspects = extract_aspects(cleaned)
    suggestions = extract_suggestions(cleaned)
    topics = [a.aspect for a in aspects if a.sentiment == NEGATIVE]
    priority = _priority(sentiment, aspects, rating)
    impact, signals = _business_impact(aspects)

    # The recommended action targets the strongest negative cost-bearing aspect.
    action, detail = "", ""
    negatives = [a for a in aspects if a.sentiment == NEGATIVE]
    if negatives:
        negatives.sort(
            key=lambda a: (a.aspect not in _COST_BEARING, a.sentiment_score)
        )
        top = negatives[0]
        problem, recommendation = ASPECT_RECOMMENDATION.get(
            top.aspect, ("", "")
        )
        action = problem
        detail = recommendation
    else:
        action = "No corrective action required."
        detail = (
            "Consider using this review as positive social proof on the product page."
        )

    return ReviewIntelligence(
        text=cleaned,
        language=sentiment.language,
        sentiment=sentiment,
        aspects=aspects,
        suggestions=suggestions,
        topics=topics,
        priority=priority,
        business_impact=impact,
        risk_signals=signals,
        recommended_action=action,
        recommended_action_detail=detail,
    )
