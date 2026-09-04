"""Customer suggestion extraction.

A suggestion is an *explicit improvement request*, not merely a complaint. The
extractor requires a request pattern ("please improve...", "you should...",
"would be better if...", "I suggest...", "need faster...") to fire, so a review
that only says "delivery was slow" produces a DELIVERY complaint but not a
suggestion. Nothing is invented that the review does not actually ask for.

Each extracted suggestion keeps its source span, and is normalised to a short
canonical action so that suggestions can be counted across thousands of reviews.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .aspects import find_aspects
from .preprocess import clean_text, split_clauses

# Request/imperative patterns. Ordered so more specific forms match first.
_REQUEST_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\b(?:please|kindly|pls)\s+(?P<body>[a-z][^.!?]{2,120})", re.I),
    re.compile(r"\b(?:you|they|seller|company)\s+(?:should|must|need to|ought to)\s+(?P<body>[a-z][^.!?]{2,120})", re.I),
    re.compile(r"\b(?:would|will|it'?d)\s+be\s+(?:much\s+)?better\s+if\s+(?P<body>[a-z][^.!?]{2,120})", re.I),
    re.compile(r"\bi\s+(?:suggest|recommend|request)\s+(?:that\s+)?(?P<body>[a-z][^.!?]{2,120})", re.I),
    re.compile(r"\b(?:need|needs|want)\s+(?P<body>(?:faster|better|quicker|stronger|more|proper|accurate)[^.!?]{2,120})", re.I),
    re.compile(r"\b(?:hope|hoping)\s+(?:you|they)\s+(?:will\s+)?(?P<body>[a-z][^.!?]{2,120})", re.I),
    re.compile(r"^\s*(?P<body>(?:improve|fix|update|add|provide|upgrade|speed up|reconsider)\b[^.!?]{2,120})", re.I),
]

# Canonical action per (aspect, matched verb family). Keeps aggregation stable.
_NORMALISERS: list[tuple[re.Pattern[str], str, str]] = [
    (re.compile(r"\b(deliver\w*|ship\w*|courier|dispatch)\b.*\b(fast|quick|speed|soon|early)\b|\b(fast|quick|speed)\w*\b.*\b(deliver\w*|ship\w*)\b", re.I), "DELIVERY", "Improve delivery speed"),
    (re.compile(r"\b(deliver\w*|ship\w*|courier)\b", re.I), "DELIVERY", "Improve delivery reliability"),
    (re.compile(r"\b(pack\w*|box|carton|bubble wrap|padding|parcel)\b", re.I), "PACKAGING", "Improve packaging"),
    (re.compile(r"\b(size chart|sizing|measurement\w*|fit guide|size)\b", re.I), "SIZE_FIT", "Improve size chart and measurements"),
    (re.compile(r"\b(quality|material|fabric|stitch\w*|qc|quality check\w*)\b", re.I), "PRODUCT_QUALITY", "Improve product quality control"),
    (re.compile(r"\b(support|customer care|customer service|helpline|chat|respon\w*)\b", re.I), "CUSTOMER_SUPPORT", "Improve customer support responsiveness"),
    (re.compile(r"\b(payment|gateway|upi|card|emi|checkout payment)\b", re.I), "PAYMENT", "Fix payment options and gateway errors"),
    (re.compile(r"\b(website|app|page|cart|login|checkout page)\b", re.I), "WEBSITE", "Fix website / app checkout issues"),
    (re.compile(r"\b(refund|return\w*|pickup|exchange|replacement)\b", re.I), "RETURNS", "Speed up returns and refunds"),
    (re.compile(r"\b(price|pricing|discount|cost|cheaper)\b", re.I), "PRICE", "Reconsider pricing / offer better discounts"),
]


@dataclass
class SuggestionResult:
    aspect: str
    suggestion_text: str
    normalized_suggestion: str
    source_span: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "aspect": self.aspect,
            "suggestion_text": self.suggestion_text,
            "normalized_suggestion": self.normalized_suggestion,
            "source_span": self.source_span,
        }


def _normalise(body: str, clause: str) -> tuple[str, str] | None:
    """Map a raw request to (aspect, canonical action)."""
    for pattern, aspect, canonical in _NORMALISERS:
        if pattern.search(body):
            return aspect, canonical
    # Fall back to whichever aspect the surrounding clause is about.
    found = find_aspects(clause)
    if found:
        aspect = found[0]
        for pattern, asp, canonical in _NORMALISERS:
            if asp == aspect:
                return aspect, canonical
    return None


def extract_suggestions(text: str) -> list[SuggestionResult]:
    """Return every explicit improvement request found in the review."""
    cleaned = clean_text(text)
    if not cleaned:
        return []

    out: list[SuggestionResult] = []
    seen: set[str] = set()

    for clause in split_clauses(cleaned):
        for pattern in _REQUEST_PATTERNS:
            match = pattern.search(clause)
            if not match:
                continue
            body = match.group("body").strip(" ,.;:")
            if len(body) < 3:
                continue
            mapped = _normalise(body, clause)
            if mapped is None:
                continue
            aspect, canonical = mapped
            if canonical in seen:
                continue
            seen.add(canonical)
            # Present the request as a readable imperative.
            phrase = body[0].upper() + body[1:]
            out.append(
                SuggestionResult(
                    aspect=aspect,
                    suggestion_text=phrase,
                    normalized_suggestion=canonical,
                    source_span=clause,
                )
            )
            break  # one suggestion per clause

    return out
