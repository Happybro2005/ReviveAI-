"""Aspect extraction and aspect-level sentiment (ABSA).

Method: segment the review into clauses, detect which aspects each clause
mentions via the domain lexicon, score that clause independently, and attach the
clause score to the aspects it mentions. An aspect's final polarity is the
mention-weighted mean of the clauses that mentioned it, so
"quality is excellent but delivery took 8 days" yields
PRODUCT_QUALITY -> positive and DELIVERY -> negative from the same review.

The evidence span is kept for every aspect so the UI can show *why* an aspect
was scored the way it was, rather than asserting it.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .lexicon import ASPECT_PATTERNS, ASPECT_RISK_SIGNAL, NEGATIONS
from .preprocess import clean_text, split_clauses, tokenize
from .sentiment import NEGATIVE, NEUTRAL, POSITIVE, score_clause

# An aspect mentioned in a clause with no opinion words still counts as a
# mention, but only aspects with a non-trivial score become signals.
_POS = 0.20
_NEG = -0.20


@dataclass
class AspectResult:
    aspect: str
    sentiment: str
    sentiment_score: float
    evidence_span: str
    mentions: int
    risk_signal: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "aspect": self.aspect,
            "sentiment": self.sentiment,
            "sentiment_score": round(self.sentiment_score, 4),
            "evidence_span": self.evidence_span,
            "mentions": self.mentions,
            "risk_signal": self.risk_signal,
        }


def find_aspects(clause: str) -> list[str]:
    """Which aspects a single clause mentions."""
    return [a for a, pattern in ASPECT_PATTERNS.items() if pattern.search(clause)]


def _negation_adjustment(clause: str, score: float) -> float:
    """Damp a positive score in a clause that is explicitly negated.

    VADER handles most negation, but commerce phrasings like "did not fit" and
    "never delivered" benefit from an extra check on low-magnitude scores.
    """
    if abs(score) >= 0.35:
        return score
    tokens = set(tokenize(clause))
    if tokens & NEGATIONS:
        return score - 0.30 if score >= 0 else score
    return score


def extract_aspects(text: str) -> list[AspectResult]:
    """Extract every aspect mentioned in the review with its own sentiment."""
    cleaned = clean_text(text)
    if not cleaned:
        return []

    buckets: dict[str, dict[str, Any]] = {}
    for clause in split_clauses(cleaned):
        mentioned = find_aspects(clause)
        if not mentioned:
            continue
        raw = score_clause(clause)
        score = _negation_adjustment(clause, raw)
        for aspect in mentioned:
            b = buckets.setdefault(
                aspect, {"scores": [], "spans": [], "mentions": 0}
            )
            b["scores"].append(score)
            b["mentions"] += 1
            b["spans"].append(clause)

    results: list[AspectResult] = []
    for aspect, b in buckets.items():
        scores: list[float] = b["scores"]
        mean = sum(scores) / len(scores)
        if mean >= _POS:
            label = POSITIVE
        elif mean <= _NEG:
            label = NEGATIVE
        else:
            label = NEUTRAL
        # Show the clause that most drove the verdict.
        if label == NEGATIVE:
            span = b["spans"][scores.index(min(scores))]
        elif label == POSITIVE:
            span = b["spans"][scores.index(max(scores))]
        else:
            span = b["spans"][0]
        results.append(
            AspectResult(
                aspect=aspect,
                sentiment=label,
                sentiment_score=mean,
                evidence_span=span,
                mentions=b["mentions"],
                risk_signal=ASPECT_RISK_SIGNAL.get(aspect) if label == NEGATIVE else None,
            )
        )

    # Most strongly felt aspects first.
    results.sort(key=lambda r: (-abs(r.sentiment_score), r.aspect))
    return results
