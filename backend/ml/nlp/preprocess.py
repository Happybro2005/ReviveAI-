"""Text preprocessing and clause segmentation.

Clause segmentation is what makes aspect-level sentiment possible: a review like
"quality is excellent but delivery took 8 days" has to be split at "but" so the
positive score attaches to PRODUCT_QUALITY and the negative one to DELIVERY.
"""
from __future__ import annotations

import re
import unicodedata

MAX_TEXT_CHARS = 8000

# Split on sentence enders and on contrastive/additive connectives, keeping the
# connective out of the emitted clause.
_CLAUSE_SPLIT = re.compile(
    r"(?:[.!?;\n]+)|(?<=\s)(?:but|however|although|though|whereas|while|and then|also)(?=\s)",
    re.IGNORECASE,
)

_WS = re.compile(r"\s+")

# Devanagari, Bengali, Tamil, Telugu, Gujarati, Kannada, Malayalam blocks.
_INDIC = re.compile(r"[ऀ-ൿ]")
_LATIN = re.compile(r"[A-Za-z]")

# Common romanised-Hindi markers, used only to flag "hi-Latn" for reporting.
_HI_LATN_MARKERS = {
    "nahi", "hai", "bahut", "accha", "achha", "kharab", "paisa", "kitna",
    "bhai", "kripya", "jaldi", "bilkul", "milega", "kyun", "lekin",
}


def clean_text(text: str) -> str:
    """Normalise unicode, collapse whitespace, and cap pathological lengths."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", str(text))
    text = text.replace("​", "").replace("﻿", "")
    text = _WS.sub(" ", text).strip()
    if len(text) > MAX_TEXT_CHARS:
        text = text[:MAX_TEXT_CHARS].rsplit(" ", 1)[0]
    return text


def detect_language(text: str) -> str:
    """Script-and-marker heuristic. Returns 'en', 'hi', 'hi-Latn', 'mixed' or 'und'.

    This is a heuristic, not a trained language ID model, and the API reports it
    as such.
    """
    if not text:
        return "und"
    indic = len(_INDIC.findall(text))
    latin = len(_LATIN.findall(text))
    if indic and latin:
        return "mixed" if indic > 3 and latin > 3 else ("hi" if indic > latin else "en")
    if indic:
        return "hi"
    if not latin:
        return "und"
    tokens = {t.strip(".,!?").lower() for t in text.split()}
    if len(tokens & _HI_LATN_MARKERS) >= 2:
        return "hi-Latn"
    return "en"


def split_clauses(text: str) -> list[str]:
    """Split a review into clauses suitable for aspect-scoped scoring."""
    if not text:
        return []
    raw = _CLAUSE_SPLIT.split(text)
    clauses = []
    for part in raw:
        if part is None:
            continue
        part = part.strip(" ,;:-")
        # Drop fragments too short to carry an opinion.
        if len(part) >= 3 and _LATIN.search(part):
            clauses.append(part)
    return clauses or ([text.strip()] if text.strip() else [])


def tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z']+", text.lower())
