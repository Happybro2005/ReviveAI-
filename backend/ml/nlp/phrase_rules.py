"""Domain phrase rules for commerce complaints that carry no opinion words.

A general-purpose sentiment lexicon scores "delivery took 8 days" and "size runs
smaller than the chart" as neutral, because neither contains an opinion word.
In a commerce context both are unambiguous complaints. These regex rules supply
that missing domain knowledge as an additive polarity adjustment on top of the
lexicon score.

Each rule is (pattern, weight). Weights are in the same -1..1 space as the VADER
compound score and are summed, then the total is clamped.
"""
from __future__ import annotations

import re

# ---- negative commerce phrasings ----
NEGATIVE_PHRASES: list[tuple[re.Pattern[str], float]] = [
    # Delivery timing stated as a fact
    (re.compile(r"\btook\s+(?:almost\s+|nearly\s+|over\s+)?\d+\s*(?:\+)?\s*(?:days?|weeks?)", re.I), -0.45),
    (re.compile(r"\b\d+\s*(?:days?|weeks?)\s+(?:to\s+(?:arrive|deliver|reach)|late|delay)", re.I), -0.45),
    (re.compile(r"\b(?:delayed|delay)\s+by\b", re.I), -0.40),
    (re.compile(r"\btook\s+(?:too|so|very|really)\s+long\b|\btoo\s+long\s+to\s+(?:arrive|deliver|reach)", re.I), -0.45),
    (re.compile(r"\b(?:very|extremely|painfully)\s+slow\b|\bages\s+to\s+(?:arrive|deliver)", re.I), -0.40),
    (re.compile(r"\bwaited?\s+(?:for\s+)?(?:over|almost|nearly)?\s*\d*\s*(?:days?|weeks?|month)", re.I), -0.35),
    (re.compile(r"\b(?:still|yet)\s+(?:not|haven'?t|hasn'?t)\s+(?:received|arrived|delivered|credited|refunded)", re.I), -0.55),
    (re.compile(r"\bnever\s+(?:arrived|delivered|received|responded|replied|came|showed up)", re.I), -0.60),
    (re.compile(r"\btracking\s+(?:was\s+)?(?:never|not)\s+updated", re.I), -0.40),
    (re.compile(r"\bkept?\s+(?:postponing|rescheduling|delaying)", re.I), -0.45),

    # Size / fit stated as a fact
    (re.compile(r"\bruns?\s+(?:much\s+|way\s+|a bit\s+)?(?:small(?:er)?|large?r?|tight|big(?:ger)?)", re.I), -0.45),
    (re.compile(r"\b(?:one|two|a)\s+size[s]?\s+(?:small(?:er)?|big(?:ger)?|large?r?)", re.I), -0.40),
    (re.compile(r"\b(?:too|very)\s+(?:tight|small|loose|big|large)\b", re.I), -0.40),
    (re.compile(r"\bdoes\s*n[o']?t\s+match\b|\bdoesn'?t\s+match\b|\bnot\s+match(?:ing)?\b", re.I), -0.50),
    (re.compile(r"\bnot\s+as\s+(?:described|shown|advertised|pictured)", re.I), -0.55),
    (re.compile(r"\bdifferent\s+from\s+the\s+(?:picture|image|description)", re.I), -0.45),
    (re.compile(r"\bmisleading\b", re.I), -0.45),

    # Condition on arrival
    (re.compile(r"\barrived\s+(?:crushed|torn|open|damaged|broken|wet|dented)", re.I), -0.55),
    (re.compile(r"\b(?:box|parcel|packet|package|packaging)\s+(?:was\s+)?(?:torn|crushed|damaged|open|broken)", re.I), -0.50),
    (re.compile(r"\bfalling\s+apart\b|\bcame\s+(?:apart|loose|off)\b", re.I), -0.50),
    (re.compile(r"\bstopped\s+working\b|\bwithin\s+a\s+(?:week|day|month)\b", re.I), -0.35),

    # Payment / site
    (re.compile(r"\b(?:payment|transaction)\s+failed\b|\bfailed\s+\w+\s+times\b", re.I), -0.50),
    (re.compile(r"\bdebited\b.*\bnot\s+confirmed\b|\bmoney\s+(?:was\s+)?deducted\b", re.I), -0.55),
    (re.compile(r"\bkept?\s+(?:crashing|resetting|failing|logging me out|throwing errors)", re.I), -0.50),

    # Support / returns
    (re.compile(r"\bno\s+(?:one|body)\s+(?:picks?\s+up|responded|replied|came)", re.I), -0.55),
    (re.compile(r"\bchasing\s+(?:support|them|customer care)\b", re.I), -0.45),
    (re.compile(r"\b(?:rejected|declined)\s+without\s+(?:any\s+)?reason", re.I), -0.50),
    (re.compile(r"\bhad\s+to\s+return\b", re.I), -0.35),
]

# ---- positive commerce phrasings ----
POSITIVE_PHRASES: list[tuple[re.Pattern[str], float]] = [
    (re.compile(r"\btrue\s+to\s+size\b", re.I), 0.45),
    (re.compile(r"\bfits?\s+(?:exactly|perfectly)\b|\bperfect\s+fit\b", re.I), 0.45),
    (re.compile(r"\bon\s+time\b|\bahead\s+of\s+schedule\b|\bearlier\s+than\s+promised\b", re.I), 0.40),
    (re.compile(r"\bwell\s+(?:packed|packaged)\b|\bsecurely\s+packed\b", re.I), 0.40),
    (re.compile(r"\bvalue\s+for\s+money\b|\bworth\s+every\b", re.I), 0.45),
    (re.compile(r"\bhassle[\s-]?free\b|\bno\s+issues?\b", re.I), 0.40),
    (re.compile(r"\bexactly\s+(?:what|as)\s+(?:i\s+)?(?:wanted|described|shown)", re.I), 0.40),
]

# A clause that asks for an improvement implies the thing is currently lacking,
# even when the request itself uses a positive verb ("please improve...").
REQUEST_MARKERS = re.compile(
    r"\b(?:please|kindly|pls)\b"
    r"|\b(?:you|they|seller|company)\s+(?:should|must|need to|ought to)\b"
    r"|\bwould\s+be\s+better\s+if\b"
    r"|\bi\s+(?:suggest|recommend|request)\b"
    r"|\bneed\s+(?:faster|better|quicker|stronger|more|proper|accurate)\b"
    r"|\bhop(?:e|ing)\s+(?:you|they)\b",
    re.I,
)

# Ceiling applied to a request clause's polarity: a request never reads as praise.
REQUEST_POLARITY_CEILING = -0.30


def phrase_adjustment(clause: str) -> float:
    """Total domain polarity adjustment for a clause."""
    total = 0.0
    for pattern, weight in NEGATIVE_PHRASES:
        if pattern.search(clause):
            total += weight
    for pattern, weight in POSITIVE_PHRASES:
        if pattern.search(clause):
            total += weight
    return total


def is_request(clause: str) -> bool:
    """True when the clause is an explicit improvement request."""
    return bool(REQUEST_MARKERS.search(clause))
