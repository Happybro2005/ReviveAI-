"""Review sentiment.

Two independent signals are combined, and the platform is explicit about what
each one is:

1. A VADER lexicon scorer extended with commerce-domain terms. Rule-based,
   deterministic, and works on any text with no training data.
2. A TF-IDF + LogisticRegression classifier trained by scripts/train_models.py on
   reviews labelled by their *star rating* (1-2 negative, 3 neutral, 4-5
   positive). The rating is a genuine human label supplied with the review, not
   a label we invented, so this is ordinary supervised learning.

If the trained classifier has not been built yet, the lexicon scorer runs alone
and `model_version` reports "lexicon-only" so the UI never implies otherwise.

MIXED is decided structurally: a review is MIXED when it carries clauses of both
polarities with meaningful strength, which is why clause segmentation happens
before scoring rather than after.
"""
from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from .lexicon import DOMAIN_SENTIMENT
from .phrase_rules import REQUEST_POLARITY_CEILING, is_request, phrase_adjustment
from .preprocess import clean_text, detect_language, split_clauses

POSITIVE = "POSITIVE"
NEGATIVE = "NEGATIVE"
NEUTRAL = "NEUTRAL"
MIXED = "MIXED"

_CLAUSE_POS_THRESHOLD = 0.28
_CLAUSE_NEG_THRESHOLD = -0.28
_DOC_POS_THRESHOLD = 0.22
_DOC_NEG_THRESHOLD = -0.22

_analyzer: SentimentIntensityAnalyzer | None = None
_analyzer_lock = threading.Lock()


def get_analyzer() -> SentimentIntensityAnalyzer:
    """Build the VADER analyzer once and reuse it (thread-safe, cached)."""
    global _analyzer
    if _analyzer is None:
        with _analyzer_lock:
            if _analyzer is None:
                a = SentimentIntensityAnalyzer()
                a.lexicon.update(DOMAIN_SENTIMENT)
                _analyzer = a
    return _analyzer


# --------------------------------------------------------------------------
# Trained classifier (optional second opinion)
# --------------------------------------------------------------------------
_clf: Any = None
_clf_meta: dict[str, Any] = {}
_clf_loaded = False
_clf_lock = threading.Lock()


def load_classifier(artifact_dir: Path) -> tuple[Any, dict[str, Any]]:
    """Load the trained sentiment classifier if it exists. Cached after first call."""
    global _clf, _clf_meta, _clf_loaded
    if _clf_loaded:
        return _clf, _clf_meta
    with _clf_lock:
        if _clf_loaded:
            return _clf, _clf_meta
        model_path = Path(artifact_dir) / "sentiment_clf.joblib"
        meta_path = Path(artifact_dir) / "sentiment_clf.json"
        if model_path.exists():
            try:
                import joblib

                _clf = joblib.load(model_path)
                if meta_path.exists():
                    _clf_meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except Exception:  # a broken artifact must not take the API down
                _clf, _clf_meta = None, {}
        _clf_loaded = True
    return _clf, _clf_meta


def reset_classifier_cache() -> None:
    """Used by training and tests after an artifact is rewritten."""
    global _clf, _clf_meta, _clf_loaded
    with _clf_lock:
        _clf, _clf_meta, _clf_loaded = None, {}, False


@dataclass
class ClauseSentiment:
    text: str
    score: float
    label: str


@dataclass
class SentimentResult:
    sentiment: str
    sentiment_score: float          # -1..1 polarity
    confidence: float               # 0..1
    language: str
    clauses: list[ClauseSentiment] = field(default_factory=list)
    lexicon_score: float = 0.0
    model_label: str | None = None
    model_confidence: float | None = None
    model_version: str = "lexicon-only"

    def to_dict(self) -> dict[str, Any]:
        return {
            "sentiment": self.sentiment,
            "sentiment_score": round(self.sentiment_score, 4),
            "confidence": round(self.confidence, 4),
            "language": self.language,
            "lexicon_score": round(self.lexicon_score, 4),
            "model_label": self.model_label,
            "model_confidence": (
                round(self.model_confidence, 4) if self.model_confidence is not None else None
            ),
            "model_version": self.model_version,
            "clauses": [
                {"text": c.text, "score": round(c.score, 4), "label": c.label}
                for c in self.clauses
            ],
        }


def score_clause(clause: str) -> float:
    """Polarity for one clause in -1..1.

    VADER compound score plus the domain phrase adjustment, so factual commerce
    complaints that carry no opinion words ("took 8 days", "runs smaller than
    the chart") are scored as the complaints they are.
    """
    base = float(get_analyzer().polarity_scores(clause)["compound"])
    adjusted = base + phrase_adjustment(clause)
    if is_request(clause):
        # Asking for an improvement is never praise for the current state.
        adjusted = min(adjusted, REQUEST_POLARITY_CEILING)
    return max(-1.0, min(1.0, adjusted))


def _label_for(score: float) -> str:
    if score >= _CLAUSE_POS_THRESHOLD:
        return POSITIVE
    if score <= _CLAUSE_NEG_THRESHOLD:
        return NEGATIVE
    return NEUTRAL


def analyze_sentiment(text: str, artifact_dir: Path | None = None) -> SentimentResult:
    """Full document sentiment with clause breakdown."""
    cleaned = clean_text(text)
    language = detect_language(cleaned)
    if not cleaned:
        return SentimentResult(NEUTRAL, 0.0, 0.0, language)

    clause_texts = split_clauses(cleaned)
    clauses = [
        ClauseSentiment(text=c, score=(s := score_clause(c)), label=_label_for(s))
        for c in clause_texts
    ]

    # Document polarity is the mean of the adjusted clause scores rather than a
    # raw pass over the whole string, so the domain phrase rules and the request
    # ceiling apply at document level too.
    if clauses:
        doc_score = sum(c.score for c in clauses) / len(clauses)
    else:
        doc_score = float(get_analyzer().polarity_scores(cleaned)["compound"])
    pos = [c for c in clauses if c.label == POSITIVE]
    neg = [c for c in clauses if c.label == NEGATIVE]

    # Structural MIXED: both polarities genuinely present.
    if pos and neg:
        label = MIXED
    elif doc_score >= _DOC_POS_THRESHOLD:
        label = POSITIVE
    elif doc_score <= _DOC_NEG_THRESHOLD:
        label = NEGATIVE
    else:
        label = NEUTRAL

    # Lexicon confidence: strength of the document signal, plus a penalty when
    # the review is internally contradictory.
    confidence = min(1.0, abs(doc_score) * 1.15 + 0.25)
    if label == MIXED:
        confidence = min(1.0, 0.45 + 0.1 * (len(pos) + len(neg)))

    model_label: str | None = None
    model_conf: float | None = None
    version = "lexicon-only"

    if artifact_dir is not None:
        clf, meta = load_classifier(artifact_dir)
        if clf is not None:
            try:
                proba = clf.predict_proba([cleaned])[0]
                classes = list(clf.classes_)
                best = int(proba.argmax())
                model_label = str(classes[best])
                model_conf = float(proba[best])
                version = meta.get("version", "sentiment-clf")
                # Agreement raises confidence; disagreement lowers it. The
                # structural MIXED verdict is never overridden by a flat 3-class
                # classifier that has no MIXED class.
                if label != MIXED:
                    if model_label == label:
                        confidence = min(1.0, (confidence + model_conf) / 2 + 0.15)
                    else:
                        confidence = max(0.05, (confidence + model_conf) / 2 - 0.20)
                        # Trust a decisive classifier over a borderline lexicon read.
                        if model_conf > 0.80 and abs(doc_score) < 0.35:
                            label = model_label
            except Exception:
                model_label, model_conf = None, None

    return SentimentResult(
        sentiment=label,
        sentiment_score=doc_score,
        confidence=round(confidence, 4),
        language=language,
        clauses=clauses,
        lexicon_score=doc_score,
        model_label=model_label,
        model_confidence=model_conf,
        model_version=version,
    )
