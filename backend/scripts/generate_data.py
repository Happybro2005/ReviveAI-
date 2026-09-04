"""Generate the synthetic ReviveAI dataset.

DISCLOSURE: every row produced here is synthetic. See SYNTHETIC_DATA_DISCLOSURE
in app/config.py -- the API surfaces that text alongside any figure derived from
this data.

Design
------
This is a *causal* simulator, not a bag of independent random columns. Latent
traits (customer price-sensitivity and return-proneness, product quality and
size-accuracy, courier reliability) drive both the observable features and the
outcomes, which is what makes the models learn a real signal:

  high shipping/cart ratio   -> higher abandonment
  payment failures           -> higher abandonment
  prior returns              -> higher return probability
  prior RTO / COD            -> higher RTO probability
  poor product size accuracy -> more size complaints AND more size returns
  slow courier               -> late deliveries AND delivery complaints in reviews

Reviews are written from the experience the simulated customer actually had, so
the Voice-of-Customer -> Revenue-Protection link is genuine.

Point-in-time correctness: sessions are replayed in chronological order per
customer, and the `prior_*` snapshot columns only ever count events that had
already happened at that moment. No outcome is ever written into a feature.

Usage:
    python scripts/generate_data.py [--reset]
"""
from __future__ import annotations

import argparse
import math
import random
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import insert, text  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.db import get_engine, session_scope  # noqa: E402
from app.models import (  # noqa: E402
    AbandonedCart,
    CheckoutSession,
    Conversion,
    Customer,
    FraudEvent,
    Intervention,
    LogisticsEvent,
    Order,
    OrderItem,
    Payment,
    Product,
    Return,
    Review,
    Shipment,
)
from scripts.review_text import compose_review  # noqa: E402

# --------------------------------------------------------------------------
# Reference data
# --------------------------------------------------------------------------
CITIES = [
    ("Mumbai", "Maharashtra", "400"), ("Delhi", "Delhi", "110"),
    ("Bengaluru", "Karnataka", "560"), ("Hyderabad", "Telangana", "500"),
    ("Chennai", "Tamil Nadu", "600"), ("Kolkata", "West Bengal", "700"),
    ("Pune", "Maharashtra", "411"), ("Ahmedabad", "Gujarat", "380"),
    ("Jaipur", "Rajasthan", "302"), ("Lucknow", "Uttar Pradesh", "226"),
    ("Patna", "Bihar", "800"), ("Guwahati", "Assam", "781"),
    ("Indore", "Madhya Pradesh", "452"), ("Kochi", "Kerala", "682"),
    ("Bhubaneswar", "Odisha", "751"),
]
# Tier-3 pincode prefixes carry more delivery friction in this simulation.
HIGH_FRICTION_PREFIXES = {"800", "781", "751", "226"}

CATEGORIES: dict[str, dict] = {
    "Apparel":      {"price": (599, 4500),   "sizes": True,  "weight": (0.2, 0.9), "return_bias": 0.55},
    "Footwear":     {"price": (899, 6500),   "sizes": True,  "weight": (0.5, 1.4), "return_bias": 0.50},
    "Electronics":  {"price": (1499, 89000), "sizes": False, "weight": (0.3, 6.0), "return_bias": -0.30},
    "Home":         {"price": (399, 12000),  "sizes": False, "weight": (0.5, 9.0), "return_bias": -0.10},
    "Beauty":       {"price": (249, 3500),   "sizes": False, "weight": (0.1, 0.6), "return_bias": -0.45},
    "Accessories":  {"price": (299, 9000),   "sizes": False, "weight": (0.1, 1.2), "return_bias": 0.05},
}
SUBCATS = {
    "Apparel": ["T-Shirt", "Kurta", "Jeans", "Jacket", "Dress", "Shirt"],
    "Footwear": ["Sneakers", "Sandals", "Formal Shoes", "Running Shoes"],
    "Electronics": ["Earbuds", "Smartwatch", "Power Bank", "Headphones", "Speaker"],
    "Home": ["Bedsheet", "Cookware", "Lamp", "Storage Box", "Curtains"],
    "Beauty": ["Serum", "Lipstick", "Face Wash", "Shampoo"],
    "Accessories": ["Backpack", "Wallet", "Sunglasses", "Belt", "Watch Strap"],
}

PAYMENT_METHODS = ["UPI", "CARD", "NETBANKING", "WALLET", "COD"]
PAYMENT_WEIGHTS = [0.42, 0.24, 0.08, 0.06, 0.20]
DEVICES = ["MOBILE", "DESKTOP", "TABLET"]
DEVICE_WEIGHTS = [0.71, 0.24, 0.05]
STAGES = ["CART", "ADDRESS", "SHIPPING", "PAYMENT", "REVIEW"]
STAGE_WEIGHTS = [0.10, 0.16, 0.20, 0.42, 0.12]
PAY_FAIL_REASONS = ["INSUFFICIENT_FUNDS", "BANK_DECLINED", "OTP_TIMEOUT", "GATEWAY_ERROR", "CARD_EXPIRED"]

# courier -> (reliability 0..1, base transit days)
COURIERS = {
    "BlueDart": (0.93, 3), "Delhivery": (0.87, 4), "Ecom Express": (0.82, 5),
    "XpressBees": (0.79, 5), "IndiaPost": (0.68, 7),
}

RECOVERY_ACTIONS = [
    "NO_ACTION", "PERSONALIZED_REMINDER", "PAYMENT_ASSISTANCE",
    "FREE_SHIPPING", "DISCOUNT_5", "DISCOUNT_10", "TECH_SUPPORT",
]
ACTION_CHANNEL = {
    "NO_ACTION": "NONE", "PERSONALIZED_REMINDER": "EMAIL",
    "PAYMENT_ASSISTANCE": "WHATSAPP", "FREE_SHIPPING": "EMAIL",
    "DISCOUNT_5": "SMS", "DISCOUNT_10": "SMS", "TECH_SUPPORT": "CALL",
}
RETURN_REASONS = ["SIZE_FIT", "QUALITY_ISSUE", "DAMAGED_IN_TRANSIT", "NOT_AS_DESCRIBED", "CHANGED_MIND", "LATE_DELIVERY"]


def sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, x))))


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


# --------------------------------------------------------------------------
# Generation
# --------------------------------------------------------------------------
class Generator:
    def __init__(self, seed: int, n_customers: int, n_products: int,
                 n_sessions: int, n_reviews: int) -> None:
        self.rng = random.Random(seed)
        self.n_customers = n_customers
        self.n_products = n_products
        self.n_sessions = n_sessions
        self.n_reviews_target = n_reviews
        self.now = datetime.now(timezone.utc).replace(microsecond=0)
        self.start = self.now - timedelta(days=540)

        # Latent traits, kept out of the database on purpose: they are the
        # unobserved causes the models must infer from observable features.
        self.cust_traits: dict[int, dict] = {}
        self.prod_traits: dict[int, dict] = {}

        self.customers: list[dict] = []
        self.products: list[dict] = []
        self.sessions: list[dict] = []
        self.carts: list[dict] = []
        self.interventions: list[dict] = []
        self.conversions: list[dict] = []
        self.orders: list[dict] = []
        self.order_items: list[dict] = []
        self.payments: list[dict] = []
        self.shipments: list[dict] = []
        self.log_events: list[dict] = []
        self.returns: list[dict] = []
        self.reviews: list[dict] = []
        self.fraud_events: list[dict] = []

    # ---------------- customers & products ----------------
    def gen_customers(self) -> None:
        r = self.rng
        for cid in range(1, self.n_customers + 1):
            city, state, prefix = r.choice(CITIES)
            signup = self.start + timedelta(days=r.randint(0, 400), hours=r.randint(0, 23))
            # Latent traits
            price_sens = clamp(r.betavariate(2.2, 2.6), 0.02, 0.98)
            return_prone = clamp(r.betavariate(1.7, 5.0), 0.01, 0.95)
            rto_prone = clamp(r.betavariate(1.4, 6.5), 0.01, 0.95)
            patience = clamp(r.betavariate(3.0, 2.2), 0.02, 0.98)
            # ~1.5% of customers behave abusively (serial returner / COD refuser).
            abusive = r.random() < 0.015
            if abusive:
                return_prone = clamp(return_prone + 0.55, 0, 0.98)
                rto_prone = clamp(rto_prone + 0.5, 0, 0.98)
            self.cust_traits[cid] = {
                "price_sens": price_sens, "return_prone": return_prone,
                "rto_prone": rto_prone, "patience": patience, "abusive": abusive,
                "high_friction": prefix in HIGH_FRICTION_PREFIXES,
                "activity": r.lognormvariate(0.0, 0.6),
            }
            self.customers.append({
                "id": cid, "external_id": f"CUST{cid:07d}",
                "name": f"Customer {cid}", "email": f"customer{cid}@example.com",
                "city": city, "state": state,
                "pincode": f"{prefix}{r.randint(100, 999)}",
                "signup_date": signup, "order_count": 0, "total_spend": 0,
                "return_count": 0, "rto_count": 0, "abandonment_count": 0,
                "delivery_failure_count": 0, "cod_refusal_count": 0, "segment": "NEW",
            })

    def gen_products(self) -> None:
        r = self.rng
        cats = list(CATEGORIES)
        for pid in range(1, self.n_products + 1):
            cat = r.choice(cats)
            meta = CATEGORIES[cat]
            lo, hi = meta["price"]
            price = round(math.exp(r.uniform(math.log(lo), math.log(hi))), 2)
            quality = clamp(r.betavariate(4.0, 2.0), 0.05, 0.99)
            size_acc = clamp(r.betavariate(3.5, 2.0), 0.05, 0.99) if meta["sizes"] else 0.95
            fragility = clamp(r.betavariate(2.0, 4.0), 0.02, 0.95)
            self.prod_traits[pid] = {
                "quality": quality, "size_acc": size_acc, "fragility": fragility,
                "return_bias": meta["return_bias"], "sizes": meta["sizes"],
                "popularity": r.lognormvariate(0.0, 0.8),
            }
            self.products.append({
                "id": pid, "sku": f"SKU-{cat[:3].upper()}-{pid:05d}",
                "title": f"{r.choice(SUBCATS[cat])} {pid}", "category": cat,
                "subcategory": r.choice(SUBCATS[cat]), "price": price,
                "cost_price": round(price * r.uniform(0.52, 0.78), 2),
                "weight_kg": round(r.uniform(*meta["weight"]), 2),
                "has_size_variants": meta["sizes"], "avg_rating": 0.0, "review_count": 0,
            })
        self.prod_weights = [self.prod_traits[p["id"]]["popularity"] for p in self.products]

    # ---------------- checkout sessions ----------------
    def gen_sessions(self) -> None:
        """Draw session timestamps, then replay chronologically per customer."""
        r = self.rng
        weights = [self.cust_traits[c["id"]]["activity"] for c in self.customers]
        cust_ids = [c["id"] for c in self.customers]

        raw: list[tuple[int, datetime]] = []
        picks = r.choices(cust_ids, weights=weights, k=self.n_sessions)
        span = (self.now - self.start).days
        for cid in picks:
            day = r.randint(0, span - 1)
            raw.append((cid, self.start + timedelta(days=day, hours=r.randint(0, 23),
                                                    minutes=r.randint(0, 59))))
        raw.sort(key=lambda t: (t[0], t[1]))

        state: dict[int, dict] = {
            cid: {"orders": 0, "abandons": 0, "returns": 0, "rto": 0,
                  "delivery_fail": 0, "cod_refusal": 0, "spend": 0.0}
            for cid in cust_ids
        }

        sid = 0
        for cid, ts in raw:
            sid += 1
            st = state[cid]
            tr = self.cust_traits[cid]
            prod = r.choices(self.products, weights=self.prod_weights, k=1)[0]
            ptr = self.prod_traits[prod["id"]]

            qty = 1 if r.random() < 0.78 else r.randint(2, 3)
            item_count = qty if r.random() < 0.7 else qty + r.randint(1, 2)
            cart_value = round(float(prod["price"]) * qty * r.uniform(0.95, 1.35), 2)

            # Shipping: free above a threshold, otherwise weight/distance driven.
            if cart_value > 1500 and r.random() < 0.6:
                shipping = 0.0
            else:
                shipping = round(40 + prod["weight_kg"] * r.uniform(18, 45)
                                 + (60 if tr["high_friction"] else 0), 2)
            ratio = round(shipping / cart_value, 4) if cart_value else 0.0

            method = r.choices(PAYMENT_METHODS, weights=PAYMENT_WEIGHTS, k=1)[0]
            device = r.choices(DEVICES, weights=DEVICE_WEIGHTS, k=1)[0]
            stage = r.choices(STAGES, weights=STAGE_WEIGHTS, k=1)[0]

            # Payment friction is itself caused (method + prior behaviour), not
            # sprinkled in independently.
            fail_base = {"UPI": 0.07, "CARD": 0.12, "NETBANKING": 0.15,
                         "WALLET": 0.06, "COD": 0.0}[method]
            fail_p = clamp(fail_base + 0.05 * (1 - tr["patience"]), 0.0, 0.6)
            payment_failed = stage in ("PAYMENT", "REVIEW") and r.random() < fail_p
            attempts = 0
            if method != "COD" and stage in ("PAYMENT", "REVIEW"):
                attempts = 1 + (r.randint(1, 3) if payment_failed else 0)

            coupon_applied = r.random() < 0.34
            coupon_failed = coupon_applied and r.random() < 0.17
            page_errors = 0
            if r.random() < 0.06:
                page_errors = r.randint(1, 4)
            address_edits = r.choices([0, 1, 2, 3], weights=[0.68, 0.2, 0.08, 0.04], k=1)[0]
            duration = int(clamp(r.lognormvariate(5.0, 0.75), 20, 3000))

            # ---- causal abandonment model ----
            z = -2.05
            z += 3.40 * clamp(ratio, 0, 0.6)
            z += 1.55 * payment_failed
            z += 0.45 * max(0, attempts - 1)
            z += 0.60 * coupon_failed
            z += 0.38 * page_errors
            z += 1.00 * tr["price_sens"] * math.log1p(cart_value / 4000.0)
            z -= 0.22 * min(st["orders"], 8)
            z += 0.28 * min(st["abandons"], 8)
            z += {"MOBILE": 0.24, "DESKTOP": 0.0, "TABLET": 0.10}[device]
            z += {"CART": 0.95, "ADDRESS": 0.50, "SHIPPING": 0.32,
                  "PAYMENT": 0.0, "REVIEW": -0.80}[stage]
            z += 0.35 * (1 - tr["patience"])  # impatient customers drop off more
            z -= 0.00035 * duration
            z += self.rng.gauss(0, 0.45)
            p_abandon = sigmoid(z)
            abandoned = r.random() < p_abandon

            self.sessions.append({
                "id": sid, "session_ref": f"CS{sid:08d}", "customer_id": cid,
                "started_at": ts, "cart_value": cart_value, "item_count": item_count,
                "shipping_cost": shipping, "shipping_cart_ratio": ratio,
                "payment_attempts": attempts, "payment_failed": payment_failed,
                "payment_method": method, "device_type": device,
                "session_duration_sec": duration, "checkout_stage": stage,
                "coupon_applied": coupon_applied, "coupon_failed": coupon_failed,
                "address_edits": address_edits, "page_errors": page_errors,
                "hour_of_day": ts.hour, "is_weekend": ts.weekday() >= 5,
                "prior_order_count": st["orders"],
                "prior_abandonment_count": st["abandons"],
                "prior_return_count": st["returns"], "prior_rto_count": st["rto"],
                "abandoned": abandoned,
            })

            # Payment attempt rows mirror the session's payment friction. On an
            # abandoned session every attempt failed; on a converted one the
            # final attempt is the one that went through.
            for a in range(1, attempts + 1):
                failed = payment_failed and (abandoned or a < attempts)
                self.payments.append({
                    "payment_ref": f"PAY{sid:08d}{a}", "order_id": None,
                    "customer_id": cid, "checkout_session_id": sid,
                    "amount": cart_value, "method": method,
                    "status": "FAILED" if failed else "SUCCESS",
                    "failure_reason": r.choice(PAY_FAIL_REASONS) if failed else None,
                    "attempt_number": a,
                    "attempted_at": ts + timedelta(seconds=duration + a * 25),
                })

            if abandoned:
                st["abandons"] += 1
                self._handle_abandonment(sid, cid, ts, cart_value, shipping, ratio,
                                         payment_failed, attempts, coupon_failed,
                                         page_errors, stage, tr, st)
            else:
                self._handle_order(sid, cid, ts, cart_value, shipping, method,
                                   prod, ptr, qty, tr, st)

        self._state = state

    # ---------------- abandonment branch ----------------
    def _handle_abandonment(self, sid, cid, ts, cart_value, shipping, ratio,
                            payment_failed, attempts, coupon_failed, page_errors,
                            stage, tr, st) -> None:
        r = self.rng
        cart_id = len(self.carts) + 1

        # Reason is determined by the strongest actual evidence present, most
        # specific evidence first. OTHER is a genuine residual, not a catch-all.
        if payment_failed or attempts > 1:
            reason = "PAYMENT_FAILURE"
        elif ratio > 0.12:
            reason = "HIGH_SHIPPING_COST"
        elif coupon_failed:
            reason = "COUPON_ISSUE"
        elif page_errors >= 2:
            reason = "TECHNICAL_PROBLEM"
        elif tr["price_sens"] > 0.55 and cart_value > 4000:
            reason = "PRICE_CONCERN"
        elif stage in ("CART", "ADDRESS", "SHIPPING") or tr["patience"] < 0.45:
            reason = "CUSTOMER_HESITATION"
        else:
            reason = "OTHER"

        self.carts.append({
            "id": cart_id, "checkout_session_id": sid, "customer_id": cid,
            "abandoned_at": ts + timedelta(minutes=r.randint(1, 40)),
            "cart_value": cart_value, "primary_reason": reason,
            "reason_confidence": None, "reason_evidence": None,
            "recovered": False, "recovered_at": None, "recovered_revenue": 0,
        })

        # Historical treatment policy: partly randomised so the recovery model
        # sees several actions per reason rather than one confounded action.
        if r.random() < 0.22:
            action = "NO_ACTION"
        elif r.random() < 0.35:
            action = r.choice(RECOVERY_ACTIONS[1:])
        else:
            action = {
                "PAYMENT_FAILURE": "PAYMENT_ASSISTANCE",
                "HIGH_SHIPPING_COST": "FREE_SHIPPING",
                "COUPON_ISSUE": "DISCOUNT_5",
                "TECHNICAL_PROBLEM": "TECH_SUPPORT",
                "PRICE_CONCERN": "DISCOUNT_10",
                "CUSTOMER_HESITATION": "PERSONALIZED_REMINDER",
                "OTHER": "PERSONALIZED_REMINDER",
            }[reason]

        # ---- causal recovery model ----
        z = -1.75
        z += {"NO_ACTION": 0.0, "PERSONALIZED_REMINDER": 0.55, "PAYMENT_ASSISTANCE": 0.70,
              "FREE_SHIPPING": 0.72, "DISCOUNT_5": 0.62, "DISCOUNT_10": 0.95,
              "TECH_SUPPORT": 0.58}[action]
        # Matching the action to the real cause is what actually pays off.
        match = {
            "PAYMENT_FAILURE": "PAYMENT_ASSISTANCE", "HIGH_SHIPPING_COST": "FREE_SHIPPING",
            "COUPON_ISSUE": "DISCOUNT_5", "TECHNICAL_PROBLEM": "TECH_SUPPORT",
            "PRICE_CONCERN": "DISCOUNT_10", "CUSTOMER_HESITATION": "PERSONALIZED_REMINDER",
            "OTHER": "PERSONALIZED_REMINDER",
        }[reason]
        if action == match and action != "NO_ACTION":
            z += 0.85
        z += 0.16 * min(st["orders"], 10)
        z -= 0.55 * tr["price_sens"]
        z -= 0.30 * math.log1p(cart_value / 8000.0)
        z += 0.25 * tr["patience"]
        z += r.gauss(0, 0.40)
        recovered = r.random() < sigmoid(z)

        cost_map = {"NO_ACTION": 0.0, "PERSONALIZED_REMINDER": 0.5, "PAYMENT_ASSISTANCE": 0.35,
                    "FREE_SHIPPING": 0.5, "DISCOUNT_5": 0.25, "DISCOUNT_10": 0.25,
                    "TECH_SUPPORT": 18.0}
        disc_map = {"DISCOUNT_5": 0.05, "DISCOUNT_10": 0.10}
        discount_cost = round(cart_value * disc_map.get(action, 0.0), 2)
        if action == "FREE_SHIPPING":
            discount_cost = shipping

        if action != "NO_ACTION":
            iv_id = len(self.interventions) + 1
            self.interventions.append({
                "id": iv_id, "abandoned_cart_id": cart_id, "order_id": None,
                "customer_id": cid, "pillar": "RECOVERY", "action": action,
                "channel": ACTION_CHANNEL[action],
                "sent_at": ts + timedelta(hours=r.randint(1, 26)),
                "predicted_probability": 0.0, "expected_revenue": 0,
                "intervention_cost": cost_map[action], "discount_cost": discount_cost,
                "expected_profit": 0, "model_version": "historical-policy",
                "outcome": "CONVERTED" if recovered else "NOT_CONVERTED",
            })
            if recovered:
                rev = round(cart_value - discount_cost, 2)
                self.conversions.append({
                    "intervention_id": iv_id, "customer_id": cid, "order_id": None,
                    "converted_at": ts + timedelta(hours=r.randint(2, 70)),
                    "revenue": rev, "realised_cost": cost_map[action] + discount_cost,
                    "realised_profit": round(rev * 0.35 - cost_map[action] - discount_cost, 2),
                })

        if recovered:
            c = self.carts[cart_id - 1]
            c["recovered"] = True
            c["recovered_at"] = ts + timedelta(hours=r.randint(2, 70))
            c["recovered_revenue"] = round(cart_value - discount_cost, 2)

    # ---------------- order / fulfilment branch ----------------
    def _handle_order(self, sid, cid, ts, cart_value, shipping, method,
                      prod, ptr, qty, tr, st) -> None:
        r = self.rng
        oid = len(self.orders) + 1
        is_cod = method == "COD"
        self.orders.append({
            "id": oid, "order_ref": f"ORD{oid:08d}", "customer_id": cid,
            "checkout_session_id": sid, "order_date": ts + timedelta(minutes=2),
            "order_value": cart_value, "shipping_cost": shipping,
            "discount_amount": 0, "payment_method": method, "is_cod": is_cod,
            "status": "PLACED",
        })
        item_id = len(self.order_items) + 1
        size = None
        if ptr["sizes"]:
            size = r.choice(["S", "M", "L", "XL", "XXL"])
        self.order_items.append({
            "id": item_id, "order_id": oid, "product_id": prod["id"],
            "quantity": qty, "unit_price": prod["price"], "selected_size": size,
        })
        if not is_cod:
            self.payments.append({
                "payment_ref": f"PAYO{oid:08d}", "order_id": oid, "customer_id": cid,
                "checkout_session_id": sid, "amount": cart_value, "method": method,
                "status": "SUCCESS", "failure_reason": None, "attempt_number": 1,
                "attempted_at": ts + timedelta(minutes=1),
            })

        st["orders"] += 1
        st["spend"] += cart_value

        # ---- shipment ----
        courier = r.choices(list(COURIERS), weights=[0.18, 0.30, 0.22, 0.18, 0.12], k=1)[0]
        reliability, base_days = COURIERS[courier]
        promised = base_days + (2 if tr["high_friction"] else 0)
        ship_id = len(self.shipments) + 1
        shipped_at = ts + timedelta(days=r.randint(0, 2), hours=r.randint(0, 12))

        # ---- causal RTO model ----
        z = -3.60
        z += 1.70 * is_cod
        z += 0.72 * min(st["rto"], 6)
        z += 0.48 * min(st["delivery_fail"], 6)
        z += 0.34 * math.log1p(cart_value / 5000.0)
        z -= 0.18 * min(st["orders"], 10)
        z += 1.30 * (1 - reliability)
        z += 0.45 * tr["high_friction"]
        z += 1.60 * tr["rto_prone"] * (1.4 if is_cod else 0.6)
        z += r.gauss(0, 0.35)
        is_rto = r.random() < sigmoid(z)

        attempts_made = 1
        if is_rto:
            attempts_made = r.randint(1, 3)
            actual_days = None
            delivered_at = None
            status = "RTO"
            rto_reason = r.choices(
                ["CUSTOMER_UNAVAILABLE", "REFUSED_COD", "ADDRESS_INCORRECT", "CUSTOMER_CANCELLED"],
                weights=[0.34, 0.32 if is_cod else 0.05, 0.20, 0.14], k=1)[0]
            st["rto"] += 1
            st["delivery_fail"] += 1
            if rto_reason == "REFUSED_COD":
                st["cod_refusal"] += 1
            self.orders[oid - 1]["status"] = "RTO"
        else:
            delay_extra = 0
            if r.random() > reliability:
                delay_extra = r.randint(1, 7)
                st["delivery_fail"] += 1 if delay_extra > 4 else 0
            actual_days = promised + delay_extra - (1 if r.random() < 0.25 else 0)
            actual_days = max(1, actual_days)
            delivered_at = shipped_at + timedelta(days=actual_days)
            status = "DELIVERED"
            rto_reason = None
            self.orders[oid - 1]["status"] = "DELIVERED"
            attempts_made = 1 if delay_extra < 3 else r.randint(1, 2)

        declared = prod["weight_kg"] * qty
        mismatch = r.random() < 0.03
        measured = round(declared * (r.uniform(1.6, 3.2) if mismatch else r.uniform(0.95, 1.08)), 2)

        self.shipments.append({
            "id": ship_id, "awb": f"AWB{ship_id:09d}", "order_id": oid,
            "customer_id": cid, "courier": courier, "shipped_at": shipped_at,
            "delivered_at": delivered_at, "promised_days": promised,
            "actual_days": actual_days, "delivery_attempts": attempts_made,
            "declared_weight_kg": round(declared, 2), "measured_weight_kg": measured,
            "status": status, "is_rto": is_rto, "rto_reason": rto_reason,
        })
        self.log_events.append({
            "shipment_id": ship_id, "event_type": "PICKED_UP", "event_at": shipped_at,
            "location": self.customers[cid - 1]["city"], "detail": courier,
        })
        if is_rto:
            self.log_events.append({
                "shipment_id": ship_id, "event_type": "DELIVERY_FAILED",
                "event_at": shipped_at + timedelta(days=promised),
                "location": self.customers[cid - 1]["city"], "detail": rto_reason,
            })
            self.log_events.append({
                "shipment_id": ship_id, "event_type": "RTO_INITIATED",
                "event_at": shipped_at + timedelta(days=promised + 2),
                "location": self.customers[cid - 1]["city"], "detail": rto_reason,
            })
        else:
            self.log_events.append({
                "shipment_id": ship_id, "event_type": "DELIVERED",
                "event_at": delivered_at, "location": self.customers[cid - 1]["city"],
                "detail": f"{actual_days}d vs {promised}d promised",
            })

        # ---- returns (delivered orders only) ----
        returned = False
        return_reason = None
        if status == "DELIVERED":
            prior_return_rate = st["returns"] / st["orders"] if st["orders"] else 0.0
            z = -3.10
            z += 1.85 * (1 - ptr["size_acc"]) if ptr["sizes"] else 0.0
            z += 1.20 * (1 - ptr["quality"])
            z += 1.55 * tr["return_prone"]
            z += 1.10 * prior_return_rate
            z += 0.28 * math.log1p(float(prod["price"]) / 3000.0)
            z += ptr["return_bias"]
            z += 0.55 * (1 if (actual_days or 0) > promised + 2 else 0)
            z += 0.85 * ptr["fragility"] * (1 if mismatch else 0)
            z += r.gauss(0, 0.35)
            if r.random() < sigmoid(z):
                returned = True
                st["returns"] += 1
                weights = [
                    3.2 if ptr["sizes"] and ptr["size_acc"] < 0.6 else 0.7,   # SIZE_FIT
                    2.0 * (1 - ptr["quality"]) + 0.3,                          # QUALITY_ISSUE
                    1.6 * ptr["fragility"],                                    # DAMAGED_IN_TRANSIT
                    0.9,                                                       # NOT_AS_DESCRIBED
                    0.8,                                                       # CHANGED_MIND
                    1.4 if (actual_days or 0) > promised + 2 else 0.15,        # LATE_DELIVERY
                ]
                return_reason = r.choices(RETURN_REASONS, weights=weights, k=1)[0]
                self.returns.append({
                    "return_ref": f"RET{len(self.returns) + 1:08d}", "order_id": oid,
                    "order_item_id": item_id, "customer_id": cid,
                    "product_id": prod["id"],
                    "requested_at": delivered_at + timedelta(days=r.randint(1, 12)),
                    "reason": return_reason, "refund_amount": cart_value,
                    "status": r.choice(["COMPLETED", "COMPLETED", "COMPLETED", "REJECTED"]),
                })
                self.orders[oid - 1]["status"] = "RETURNED"

        # ---- review, written from the experience above ----
        if status == "DELIVERED" and r.random() < 0.86:
            self._make_review(cid, oid, prod, ptr, actual_days, promised,
                              returned, return_reason, mismatch, delivered_at)

    # ---------------- reviews ----------------
    def _make_review(self, cid, oid, prod, ptr, actual_days, promised,
                     returned, return_reason, weight_mismatch, delivered_at) -> None:
        r = self.rng
        pos: list[str] = []
        neg: list[str] = []
        sugg: list[str] = []
        delay = (actual_days or 0) - promised

        # Delivery
        if delay >= 2:
            neg.append("DELIVERY")
            if r.random() < 0.45:
                sugg.append("DELIVERY")
        elif delay <= 0 and r.random() < 0.5:
            pos.append("DELIVERY")

        # Packaging: driven by fragility and weight-mismatch handling issues.
        pack_bad = r.random() < clamp(0.06 + 0.45 * ptr["fragility"]
                                      + (0.20 if weight_mismatch else 0), 0, 0.85)
        if pack_bad:
            neg.append("PACKAGING")
            if r.random() < 0.4:
                sugg.append("PACKAGING")
        elif r.random() < 0.3:
            pos.append("PACKAGING")

        # Size/fit: caused by the product's true size accuracy.
        if ptr["sizes"]:
            if return_reason == "SIZE_FIT" or r.random() < (1 - ptr["size_acc"]) * 0.75:
                neg.append("SIZE_FIT")
                if r.random() < 0.5:
                    sugg.append("SIZE_FIT")
            elif r.random() < 0.35:
                pos.append("SIZE_FIT")

        # Quality
        if return_reason in ("QUALITY_ISSUE", "NOT_AS_DESCRIBED") or r.random() < (1 - ptr["quality"]) * 0.8:
            neg.append("PRODUCT_QUALITY")
            if r.random() < 0.3:
                sugg.append("PRODUCT_QUALITY")
        elif r.random() < 0.65:
            pos.append("PRODUCT_QUALITY")

        # Support / price
        if returned and r.random() < 0.35:
            neg.append("CUSTOMER_SUPPORT")
            if r.random() < 0.4:
                sugg.append("CUSTOMER_SUPPORT")
        if r.random() < 0.12:
            (neg if r.random() < 0.6 else pos).append("PRICE")

        if not pos and not neg:
            pos.append("PRODUCT_QUALITY")

        text_body = compose_review(r, pos, neg, delay_days=actual_days,
                                   suggestion_aspects=sugg)

        # Rating follows the balance of experience, with realistic noise.
        score = len(pos) - 1.35 * len(neg)
        if score >= 2:
            rating = r.choices([5, 4], weights=[0.75, 0.25])[0]
        elif score >= 0.5:
            rating = r.choices([4, 5, 3], weights=[0.6, 0.2, 0.2])[0]
        elif score >= -0.5:
            rating = r.choices([3, 4, 2], weights=[0.55, 0.25, 0.20])[0]
        elif score >= -2:
            rating = r.choices([2, 3, 1], weights=[0.5, 0.25, 0.25])[0]
        else:
            rating = r.choices([1, 2], weights=[0.7, 0.3])[0]

        rid = len(self.reviews) + 1
        self.reviews.append({
            "id": rid, "review_ref": f"REV{rid:08d}", "customer_id": cid,
            "product_id": prod["id"], "order_id": oid, "rating": rating,
            "review_text": text_body,
            "review_date": delivered_at + timedelta(days=r.randint(1, 20)),
            "source": "SEED",
        })

    # ---------------- anomalies ----------------
    def gen_fraud_events(self) -> None:
        """Rule-triggered anomalies. The IsolationForest layer is trained later
        in train_models.py; these rows are the rule-based half of the hybrid."""
        r = self.rng
        by_customer: dict[int, dict] = {}
        for s in self.shipments:
            d = by_customer.setdefault(s["customer_id"], {"rto": 0, "ships": 0, "mismatch": 0})
            d["ships"] += 1
            d["rto"] += 1 if s["is_rto"] else 0
            if s["declared_weight_kg"] and abs(s["measured_weight_kg"] - s["declared_weight_kg"]) / s["declared_weight_kg"] > 0.5:
                d["mismatch"] += 1
        returns_by_cust: dict[int, int] = {}
        for ret in self.returns:
            returns_by_cust[ret["customer_id"]] = returns_by_cust.get(ret["customer_id"], 0) + 1
        orders_by_cust: dict[int, int] = {}
        for o in self.orders:
            orders_by_cust[o["customer_id"]] = orders_by_cust.get(o["customer_id"], 0) + 1

        for cid, d in by_customer.items():
            rules: list[str] = []
            orders_n = orders_by_cust.get(cid, 0)
            rets = returns_by_cust.get(cid, 0)
            if orders_n >= 4 and rets / orders_n > 0.6:
                rules.append("RETURN_RATE_ABOVE_60PCT")
            if d["ships"] >= 4 and d["rto"] / d["ships"] > 0.5:
                rules.append("RTO_RATE_ABOVE_50PCT")
            if self.cust_traits[cid]["abusive"] and d["rto"] >= 3:
                rules.append("REPEATED_COD_REFUSAL")
            if not rules:
                continue
            exposure = sum(float(o["order_value"]) for o in self.orders
                           if o["customer_id"] == cid and o["status"] in ("RTO", "RETURNED"))
            self.fraud_events.append({
                "customer_id": cid, "order_id": None, "shipment_id": None,
                "detected_at": self.now, "anomaly_class": "CUSTOMER_BEHAVIOR",
                "anomaly_score": round(clamp(0.4 + 0.15 * len(rules), 0, 1), 4),
                "risk_level": "HIGH" if len(rules) >= 2 else "MEDIUM",
                "triggered_rules": "|".join(rules),
                "evidence": f"orders={orders_n} returns={rets} shipments={d['ships']} rto={d['rto']}",
                "recommended_action": "MANUAL_REVIEW" if len(rules) >= 2 else "ORDER_CONFIRMATION",
                "estimated_exposure": round(exposure, 2), "model_version": "rules-v1",
            })

        for s in self.shipments:
            if not s["declared_weight_kg"]:
                continue
            ratio = abs(s["measured_weight_kg"] - s["declared_weight_kg"]) / s["declared_weight_kg"]
            if ratio > 0.5:
                self.fraud_events.append({
                    "customer_id": s["customer_id"], "order_id": s["order_id"],
                    "shipment_id": s["id"], "detected_at": s["shipped_at"],
                    "anomaly_class": "LOGISTICS_OPERATIONAL",
                    "anomaly_score": round(clamp(ratio / 3.0, 0, 1), 4),
                    "risk_level": "HIGH" if ratio > 1.5 else "MEDIUM",
                    "triggered_rules": "WEIGHT_MISMATCH",
                    "evidence": f"declared={s['declared_weight_kg']}kg measured={s['measured_weight_kg']}kg",
                    "recommended_action": "LOGISTICS_REVIEW",
                    "estimated_exposure": 0.0, "model_version": "rules-v1",
                })

    # ---------------- rollups ----------------
    def finalize_customers(self) -> None:
        st = self._state
        for c in self.customers:
            s = st[c["id"]]
            c["order_count"] = s["orders"]
            c["total_spend"] = round(s["spend"], 2)
            c["return_count"] = s["returns"]
            c["rto_count"] = s["rto"]
            c["abandonment_count"] = s["abandons"]
            c["delivery_failure_count"] = s["delivery_fail"]
            c["cod_refusal_count"] = s["cod_refusal"]
            if s["orders"] == 0:
                c["segment"] = "PROSPECT"
            elif s["spend"] > 60000 or s["orders"] >= 12:
                c["segment"] = "VIP"
            elif s["orders"] >= 4:
                c["segment"] = "LOYAL"
            else:
                c["segment"] = "NEW"

    def finalize_products(self) -> None:
        agg: dict[int, list[int]] = {}
        for rv in self.reviews:
            agg.setdefault(rv["product_id"], []).append(rv["rating"])
        for p in self.products:
            ratings = agg.get(p["id"], [])
            p["review_count"] = len(ratings)
            p["avg_rating"] = round(sum(ratings) / len(ratings), 3) if ratings else 0.0

    def run(self) -> None:
        t0 = time.time()
        self.gen_customers()
        print(f"  customers      {len(self.customers):>8,}  ({time.time() - t0:.1f}s)")
        self.gen_products()
        print(f"  products       {len(self.products):>8,}")
        self.gen_sessions()
        print(f"  sessions       {len(self.sessions):>8,}  ({time.time() - t0:.1f}s)")
        print(f"  abandoned      {len(self.carts):>8,}")
        print(f"  orders         {len(self.orders):>8,}")
        print(f"  shipments      {len(self.shipments):>8,}")
        print(f"  returns        {len(self.returns):>8,}")
        print(f"  reviews        {len(self.reviews):>8,}")
        self.gen_fraud_events()
        print(f"  anomalies      {len(self.fraud_events):>8,}")
        self.finalize_customers()
        self.finalize_products()
        print(f"  generation done in {time.time() - t0:.1f}s")


# --------------------------------------------------------------------------
# Persistence
# --------------------------------------------------------------------------
TRUNCATE_ORDER = [
    "conversions", "interventions", "abandoned_carts", "fraud_events",
    "logistics_events", "returns", "shipments", "review_aspects",
    "customer_suggestions", "review_analysis", "seller_recommendations",
    "product_voc_signals", "reviews", "payments", "order_items", "orders",
    "checkout_sessions", "products", "customers", "return_risk_scores",
    "rto_risk_scores",
]

SEQUENCES = [
    ("customers", "id"), ("products", "id"), ("orders", "id"), ("order_items", "id"),
    ("payments", "id"), ("checkout_sessions", "id"), ("abandoned_carts", "id"),
    ("interventions", "id"), ("conversions", "id"), ("shipments", "id"),
    ("logistics_events", "id"), ("returns", "id"), ("reviews", "id"),
    ("fraud_events", "id"),
]


def bulk_insert(session, model, rows: list[dict], label: str, chunk: int = 5000) -> None:
    if not rows:
        print(f"    {label:<18} 0")
        return
    for i in range(0, len(rows), chunk):
        session.execute(insert(model.__table__), rows[i:i + chunk])
    print(f"    {label:<18} {len(rows):,}")


def persist(gen: Generator, reset: bool) -> None:
    engine = get_engine()
    if reset:
        with engine.begin() as conn:
            conn.execute(text("TRUNCATE TABLE " + ", ".join(TRUNCATE_ORDER) + " RESTART IDENTITY CASCADE"))
        print("  existing rows truncated")

    with session_scope() as s:
        print("  writing:")
        bulk_insert(s, Customer, gen.customers, "customers")
        bulk_insert(s, Product, gen.products, "products")
        bulk_insert(s, CheckoutSession, gen.sessions, "checkout_sessions")
        bulk_insert(s, Order, gen.orders, "orders")
        bulk_insert(s, OrderItem, gen.order_items, "order_items")
        bulk_insert(s, Payment, gen.payments, "payments")
        bulk_insert(s, AbandonedCart, gen.carts, "abandoned_carts")
        bulk_insert(s, Intervention, gen.interventions, "interventions")
        bulk_insert(s, Conversion, gen.conversions, "conversions")
        bulk_insert(s, Shipment, gen.shipments, "shipments")
        bulk_insert(s, LogisticsEvent, gen.log_events, "logistics_events")
        bulk_insert(s, Return, gen.returns, "returns")
        bulk_insert(s, Review, gen.reviews, "reviews")
        bulk_insert(s, FraudEvent, gen.fraud_events, "fraud_events")

    with engine.begin() as conn:
        for table, col in SEQUENCES:
            conn.execute(text(
                f"SELECT setval(pg_get_serial_sequence('{table}', '{col}'), "
                f"COALESCE((SELECT MAX({col}) FROM {table}), 1), true)"
            ))
    print("  sequences reset")


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate synthetic ReviveAI data")
    ap.add_argument("--reset", action="store_true", help="truncate existing rows first")
    ap.add_argument("--sessions", type=int, default=None)
    ap.add_argument("--customers", type=int, default=None)
    args = ap.parse_args()

    st = get_settings()
    n_sessions = args.sessions or st.n_checkout_sessions
    n_customers = args.customers or st.n_customers

    print("ReviveAI synthetic data generator")
    print("  DISCLOSURE: all generated rows are synthetic demo data.")
    print(f"  seed={st.seed} customers={n_customers:,} sessions={n_sessions:,}")

    gen = Generator(st.seed, n_customers, st.n_products, n_sessions, st.n_reviews)
    gen.run()
    persist(gen, reset=args.reset)
    print("\nDone. Next: python scripts/train_models.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
