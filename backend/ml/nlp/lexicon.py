"""Aspect lexicons and the aspect -> business-signal mapping.

These are general commerce-domain vocabularies, not a mirror of the synthetic
review templates. They are matched with word-boundary regexes so that "fit"
does not fire on "benefit" and "size" does not fire on "sizeable".
"""
from __future__ import annotations

import re

# Canonical aspects surfaced by the platform.
ASPECTS = [
    "PRODUCT_QUALITY",
    "PRICE",
    "DELIVERY",
    "PACKAGING",
    "SIZE_FIT",
    "CUSTOMER_SUPPORT",
    "PAYMENT",
    "WEBSITE",
    "RETURNS",
]

ASPECT_LABELS = {
    "PRODUCT_QUALITY": "Product Quality",
    "PRICE": "Price",
    "DELIVERY": "Delivery",
    "PACKAGING": "Packaging",
    "SIZE_FIT": "Size / Fit",
    "CUSTOMER_SUPPORT": "Customer Support",
    "PAYMENT": "Payment",
    "WEBSITE": "Website / App",
    "RETURNS": "Returns & Refunds",
}

# Trigger terms per aspect. Multi-word phrases are matched literally.
ASPECT_TERMS: dict[str, list[str]] = {
    "PRODUCT_QUALITY": [
        "quality", "build", "material", "fabric", "stitching", "finish", "finishing",
        "durable", "durability", "defective", "defect", "broken", "damaged product",
        "cheap material", "flimsy", "sturdy", "premium", "workmanship", "texture",
        "fake", "duplicate", "original", "counterfeit", "worn out", "falling apart",
    ],
    "PRICE": [
        "price", "priced", "pricing", "expensive", "cheap price", "costly", "value for money",
        "overpriced", "worth the money", "worth every", "affordable", "budget", "rupees",
        "discount", "deal", "money", "cost too much", "value",
    ],
    "DELIVERY": [
        "delivery", "delivered", "deliver", "shipping", "shipped", "courier", "dispatch",
        "dispatched", "arrived", "arrive", "transit", "tracking", "late", "delay",
        "delayed", "slow shipping", "fast shipping", "on time", "eta", "logistics",
    ],
    "PACKAGING": [
        "packaging", "packed", "package", "packet", "box", "wrapping", "wrapped",
        "bubble wrap", "carton", "parcel", "seal", "sealed", "padding",
    ],
    # Bare adjectives ("small", "loose", "tight") are deliberately NOT listed
    # here. On their own they fire on unrelated complaints -- "the stitching
    # came loose" is a quality defect and "the item was loose inside the box" is
    # a packaging one, neither of which is a fit issue. Only terms that are
    # unambiguously about sizing, or an adjective bound to a sizing context,
    # count as SIZE_FIT.
    "SIZE_FIT": [
        "size", "sizes", "sizing", "size chart", "sizechart",
        "fit", "fits", "fitting", "fitted",
        "measurement", "measurements",
        "true to size", "runs small", "runs large", "runs big", "runs tight",
        "too small", "too large", "too big", "too tight", "too loose",
        "one size", "two sizes", "half size",
        "waist size", "chest size", "shoe size",
    ],
    "CUSTOMER_SUPPORT": [
        "support", "customer care", "customer service", "helpline", "agent",
        "representative", "chat support", "call centre", "call center", "complaint",
        "responded", "response time", "unhelpful", "rude",
    ],
    "PAYMENT": [
        "payment", "paid", "transaction", "gateway", "upi", "card declined", "debited",
        "refund amount", "cod", "cash on delivery", "emi", "netbanking", "wallet",
        "otp", "checkout payment",
    ],
    "WEBSITE": [
        "website", "site", "app", "application", "page", "checkout page", "cart",
        "login", "logged out", "crashed", "crashing", "interface", "ui", "navigation",
    ],
    "RETURNS": [
        "return", "returns", "returned", "refund", "refunded", "replacement", "exchange",
        "pickup", "return policy", "return process",
    ],
}

# Which protection signal an aspect complaint feeds. This is the bridge that
# makes Voice of Customer drive Revenue Protection rather than sit beside it.
ASPECT_RISK_SIGNAL: dict[str, str] = {
    "SIZE_FIT": "RETURN_RISK",
    "PRODUCT_QUALITY": "RETURN_RISK",
    "PACKAGING": "LOGISTICS_RISK",
    "DELIVERY": "LOGISTICS_RISK",
    "RETURNS": "LOGISTICS_RISK",
    "CUSTOMER_SUPPORT": "CX_RISK",
    "PAYMENT": "CHECKOUT_RISK",
    "WEBSITE": "CHECKOUT_RISK",
    "PRICE": "CHECKOUT_RISK",
}

# Seller action recommended when an aspect is the dominant complaint.
ASPECT_RECOMMENDATION: dict[str, tuple[str, str]] = {
    "SIZE_FIT": (
        "Customers report that sizing does not match the size chart.",
        "Re-measure the affected SKUs and publish an accurate size chart with "
        "garment measurements; add a fit guide and a 'runs small/large' note on the PDP.",
    ),
    "PRODUCT_QUALITY": (
        "Customers report quality and material defects.",
        "Tighten inbound QC on the affected SKUs, re-check the supplier batch, and "
        "correct product imagery/specifications that overstate the material.",
    ),
    "PACKAGING": (
        "Customers report parcels arriving damaged or poorly packed.",
        "Upgrade to double-wall cartons with padding for fragile SKUs and audit the "
        "courier's handling on the affected lanes.",
    ),
    "DELIVERY": (
        "Customers report slow or unreliable delivery.",
        "Review courier allocation on the affected pincodes, tighten the promised "
        "delivery window, and enable proactive delay notifications.",
    ),
    "CUSTOMER_SUPPORT": (
        "Customers report slow or unhelpful support.",
        "Add first-response SLAs and staffing for the affected queue; publish a "
        "working contact channel on the order page.",
    ),
    "PAYMENT": (
        "Customers report payment and gateway failures.",
        "Investigate gateway error codes and add a retry/alternate-method prompt at "
        "checkout; enable payment-assistance outreach on failed attempts.",
    ),
    "WEBSITE": (
        "Customers report checkout and app instability.",
        "Fix the reported checkout page errors and add session recovery so carts "
        "survive a logout or crash.",
    ),
    "RETURNS": (
        "Customers report a slow or unreliable returns and refund process.",
        "Shorten refund turnaround, confirm pickup scheduling with the courier, and "
        "publish clear return-status tracking.",
    ),
    "PRICE": (
        "Customers perceive the product as overpriced.",
        "Benchmark pricing against competing listings and test a bundled or "
        "loyalty-based offer rather than a blanket discount.",
    ),
}


def _compile(terms: list[str]) -> re.Pattern[str]:
    parts = sorted((re.escape(t) for t in terms), key=len, reverse=True)
    return re.compile(r"(?<!\w)(?:" + "|".join(parts) + r")(?!\w)", re.IGNORECASE)


ASPECT_PATTERNS: dict[str, re.Pattern[str]] = {
    aspect: _compile(terms) for aspect, terms in ASPECT_TERMS.items()
}

# Domain sentiment terms VADER does not weight well in a commerce context.
DOMAIN_SENTIMENT: dict[str, float] = {
    "defective": -2.4, "flimsy": -2.0, "overpriced": -2.0, "delayed": -1.8,
    "damaged": -2.2, "torn": -1.9, "crushed": -1.8, "misleading": -2.1,
    "unhelpful": -2.0, "rude": -2.3, "refused": -1.6, "crashed": -1.9,
    "crashing": -1.9, "slow": -1.4, "late": -1.5, "tight": -0.9, "loose": -0.8,
    "cheap": -1.1, "fake": -2.4, "duplicate": -1.8, "counterfeit": -2.4,
    "sturdy": 1.8, "premium": 1.9, "durable": 1.8, "seamless": 1.8,
    "hassle free": 2.0, "true to size": 2.0, "on time": 1.7, "well packed": 1.9,
    "value for money": 2.0, "worth every": 2.0, "prompt": 1.6,
}

NEGATIONS = {
    "not", "no", "never", "none", "nothing", "neither", "nor", "cannot", "cant",
    "can't", "won't", "wont", "didn't", "didnt", "doesn't", "doesnt", "isn't",
    "isnt", "wasn't", "wasnt", "hardly", "barely", "without",
}
