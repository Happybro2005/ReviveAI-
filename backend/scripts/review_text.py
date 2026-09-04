"""Realistic review-text synthesis.

Reviews are written *from the customer's actual experience* in the simulation:
if a shipment was late, the review can complain about delivery; if a return was
raised for a size reason, the review can complain about fit. That is what makes
the Voice-of-Customer -> Revenue-Protection link real rather than decorative.

The phrasing banks below are deliberately varied and written in ordinary English
so that the NLP pipeline is not merely reverse-engineering a fixed template set.
"""
from __future__ import annotations

import random

# --------------------------------------------------------------------------
# Clause banks: aspect -> polarity -> phrasings
# --------------------------------------------------------------------------
CLAUSES: dict[str, dict[str, list[str]]] = {
    "PRODUCT_QUALITY": {
        "pos": [
            "the product quality is excellent",
            "build quality feels premium and solid",
            "the material is genuinely good",
            "quality is much better than I expected for this price",
            "the finish is neat and the product feels durable",
            "very happy with the quality of the item",
            "the fabric feels soft and well made",
        ],
        "neg": [
            "the product quality is poor",
            "the material feels cheap and flimsy",
            "the item started falling apart within a week",
            "quality is nowhere close to what was shown in the pictures",
            "the finishing is rough and looks defective",
            "received a damaged and defective piece",
            "the stitching came loose almost immediately",
        ],
    },
    "PRICE": {
        "pos": [
            "great value for the price",
            "worth every rupee I paid",
            "reasonably priced for what you get",
            "the discount made it a really good deal",
        ],
        "neg": [
            "it is far too expensive for what it is",
            "overpriced compared to other sellers",
            "not worth the money at all",
            "the price is too high for this quality",
        ],
    },
    "DELIVERY": {
        "pos": [
            "delivery was quick and on time",
            "the order arrived a day earlier than promised",
            "shipping was fast and well tracked",
            "delivered right on schedule",
        ],
        "neg": [
            "delivery took {days} days which is far too long",
            "the order was delayed by almost a week",
            "shipping was extremely slow",
            "it took {days} days to arrive and tracking was never updated",
            "the courier kept postponing the delivery",
            "delivery was late and nobody informed me",
        ],
    },
    "PACKAGING": {
        "pos": [
            "packaging was neat and secure",
            "the item was well packed with proper padding",
            "packaging was sturdy and protected the product",
        ],
        "neg": [
            "the packaging was damaged when it arrived",
            "the box was torn and the item was loose inside",
            "packaging was flimsy and offered no protection",
            "the parcel arrived crushed and open",
        ],
    },
    "SIZE_FIT": {
        "pos": [
            "the size chart was accurate and the fit is perfect",
            "fits exactly as described",
            "true to size and very comfortable",
        ],
        "neg": [
            "the size runs much smaller than the size chart says",
            "size does not match the description at all",
            "the fit is completely wrong, I had to return it",
            "ordered my usual size but it came far too tight",
            "the measurements listed are misleading",
            "it is at least one size smaller than expected",
        ],
    },
    "CUSTOMER_SUPPORT": {
        "pos": [
            "customer support responded quickly and solved the issue",
            "the support team was polite and helpful",
            "got a refund without any argument",
        ],
        "neg": [
            "customer support never responded to my emails",
            "the support team was rude and unhelpful",
            "I have been chasing support for a week with no resolution",
            "nobody picks up the customer care number",
        ],
    },
    "PAYMENT": {
        "pos": [
            "payment went through smoothly",
            "checkout and payment were seamless",
        ],
        "neg": [
            "my payment failed three times before it finally went through",
            "the amount was debited but the order was not confirmed",
            "the payment gateway kept throwing errors",
        ],
    },
    "WEBSITE": {
        "pos": [
            "the website was easy to navigate",
            "the app worked smoothly during checkout",
        ],
        "neg": [
            "the checkout page kept crashing",
            "the website is slow and the cart kept resetting",
            "the app logged me out in the middle of payment",
        ],
    },
    "RETURNS": {
        "pos": [
            "the return process was simple and refund came fast",
            "returns were hassle free",
        ],
        "neg": [
            "the return request was rejected without any reason",
            "return pickup was scheduled three times and nobody came",
            "the refund has still not been credited",
        ],
    },
}

# Explicit improvement requests. Kept separate from complaint clauses so the
# suggestion extractor has to actually detect the imperative/request form.
SUGGESTIONS: dict[str, list[str]] = {
    "DELIVERY": [
        "Please improve delivery speed.",
        "You should use a faster courier partner.",
        "It would be better if you shipped within two days.",
        "Need faster shipping options at checkout.",
    ],
    "PACKAGING": [
        "Please improve the packaging.",
        "I suggest using bubble wrap for fragile items.",
        "You should use a stronger box.",
        "Would be better if the packaging had more padding.",
    ],
    "SIZE_FIT": [
        "Please provide accurate measurements in the size chart.",
        "You should update the size chart with actual measurements.",
        "I suggest adding a fit guide to the product page.",
        "Please improve the size chart.",
    ],
    "PRODUCT_QUALITY": [
        "Please improve the material quality.",
        "You should run better quality checks before shipping.",
        "I suggest using better fabric for this price point.",
    ],
    "CUSTOMER_SUPPORT": [
        "Please improve your customer support response time.",
        "You should provide a working helpline number.",
        "I suggest adding live chat support.",
    ],
    "PRICE": [
        "Please offer better discounts for repeat customers.",
        "You should reconsider the pricing.",
    ],
    "PAYMENT": [
        "Please add more payment options.",
        "You should fix the payment gateway errors.",
    ],
    "WEBSITE": [
        "Please fix the checkout page.",
        "You should make the app more stable.",
    ],
    "RETURNS": [
        "Please make the return process faster.",
        "You should speed up refund processing.",
    ],
}

OPENERS_POS = [
    "Really happy with this purchase.",
    "Good experience overall.",
    "Loved it.",
    "Exactly what I wanted.",
    "",
]
OPENERS_NEG = [
    "Very disappointed with this order.",
    "Not a good experience.",
    "Would not order again.",
    "Regret buying this.",
    "",
]
OPENERS_NEUTRAL = [
    "Decent product, mixed experience.",
    "It is okay.",
    "Average overall.",
    "",
]

CONNECTORS_CONTRAST = [" but ", " however ", " although ", " though "]
CONNECTORS_ADD = [" and ", ". Also ", ". "]


def _capitalize_sentences(text: str) -> str:
    """Upper-case the first letter of every sentence, including after '. '."""
    out: list[str] = []
    start_of_sentence = True
    for ch in text:
        if start_of_sentence and ch.isalpha():
            out.append(ch.upper())
            start_of_sentence = False
        else:
            out.append(ch)
            if ch in ".!?":
                start_of_sentence = True
    return "".join(out)


def _fill(template: str, rng: random.Random, delay_days: int | None) -> str:
    if "{days}" in template:
        days = delay_days if delay_days and delay_days > 0 else rng.randint(6, 12)
        return template.format(days=days)
    return template


def compose_review(
    rng: random.Random,
    positive_aspects: list[str],
    negative_aspects: list[str],
    delay_days: int | None = None,
    suggestion_aspects: list[str] | None = None,
) -> str:
    """Build a review sentence from the aspects the customer actually experienced."""
    pos_clauses = [
        _fill(rng.choice(CLAUSES[a]["pos"]), rng, delay_days)
        for a in positive_aspects
        if a in CLAUSES and CLAUSES[a]["pos"]
    ]
    neg_clauses = [
        _fill(rng.choice(CLAUSES[a]["neg"]), rng, delay_days)
        for a in negative_aspects
        if a in CLAUSES and CLAUSES[a]["neg"]
    ]

    parts: list[str] = []
    if pos_clauses and neg_clauses:
        opener = rng.choice(OPENERS_NEUTRAL)
        body = pos_clauses[0] + rng.choice(CONNECTORS_CONTRAST) + neg_clauses[0]
        extras = pos_clauses[1:] + neg_clauses[1:]
        for extra in extras:
            body += rng.choice(CONNECTORS_ADD) + extra
        parts = [opener, body]
    elif pos_clauses:
        opener = rng.choice(OPENERS_POS)
        body = pos_clauses[0]
        for extra in pos_clauses[1:]:
            body += rng.choice(CONNECTORS_ADD) + extra
        parts = [opener, body]
    elif neg_clauses:
        opener = rng.choice(OPENERS_NEG)
        body = neg_clauses[0]
        for extra in neg_clauses[1:]:
            body += rng.choice(CONNECTORS_ADD) + extra
        parts = [opener, body]
    else:
        parts = ["Product received as described. Nothing much to add."]

    text = " ".join(p for p in parts if p).strip()
    if not text.endswith((".", "!", "?")):
        text += "."
    text = _capitalize_sentences(text)

    for aspect in suggestion_aspects or []:
        if aspect in SUGGESTIONS:
            text += " " + rng.choice(SUGGESTIONS[aspect])

    return text
