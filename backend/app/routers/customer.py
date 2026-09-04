"""Customer 360 and the AI Decision Center's per-customer intelligence."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from ml.common import ModelNotTrained
from ml.decision.decision_engine import decide_protection, decide_recovery
from ml.protection import fraud_model, return_model, rto_model

from ..config import SYNTHETIC_DATA_DISCLOSURE
from ..db import get_db
from ..deps import get_costs, get_store

router = APIRouter(tags=["customer"])


@router.get("/customers")
def list_customers(
    db: Session = Depends(get_db),
    limit: int = Query(default=25, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    segment: str | None = None,
    search: str | None = None,
    has_abandoned: bool | None = None,
):
    where, params = [], {"limit": limit, "offset": offset}
    if segment:
        where.append("c.segment = :segment")
        params["segment"] = segment
    if search:
        where.append("(c.name ILIKE :q OR c.email ILIKE :q OR c.external_id ILIKE :q)")
        params["q"] = f"%{search}%"
    if has_abandoned:
        where.append("c.abandonment_count > 0")
    clause = (" WHERE " + " AND ".join(where)) if where else ""

    total = db.execute(
        text(f"SELECT COUNT(*) FROM customers c{clause}"), params
    ).scalar_one()
    rows = db.execute(text(f"""
        SELECT c.id, c.external_id, c.name, c.email, c.city, c.segment,
               c.order_count, c.total_spend, c.return_count, c.rto_count,
               c.abandonment_count
        FROM customers c{clause}
        ORDER BY c.total_spend DESC, c.id
        LIMIT :limit OFFSET :offset
    """), params).mappings().all()

    return {
        "items": [
            {**dict(r), "total_spend": float(r["total_spend"])} for r in rows
        ],
        "total": int(total), "limit": limit, "offset": offset,
        "disclosure": SYNTHETIC_DATA_DISCLOSURE,
    }


@router.get("/customer/{customer_id}")
def customer_360(customer_id: int, db: Session = Depends(get_db)):
    """Every module's view of one customer, joined from the database."""
    profile = db.execute(text("""
        SELECT id, external_id, name, email, city, state, pincode, segment,
               signup_date, order_count, total_spend, return_count, rto_count,
               abandonment_count, delivery_failure_count, cod_refusal_count
        FROM customers WHERE id = :cid
    """), {"cid": customer_id}).mappings().first()
    if profile is None:
        raise HTTPException(status_code=404, detail=f"Customer {customer_id} not found")

    orders = db.execute(text("""
        SELECT o.id, o.order_ref, o.order_date, o.order_value, o.payment_method,
               o.is_cod, o.status, s.courier, s.status AS shipment_status,
               s.is_rto, s.actual_days, s.promised_days
        FROM orders o LEFT JOIN shipments s ON s.order_id = o.id
        WHERE o.customer_id = :cid ORDER BY o.order_date DESC LIMIT 50
    """), {"cid": customer_id}).mappings().all()

    payments = db.execute(text("""
        SELECT id, payment_ref, amount, method, status, failure_reason,
               attempt_number, attempted_at
        FROM payments WHERE customer_id = :cid
        ORDER BY attempted_at DESC LIMIT 50
    """), {"cid": customer_id}).mappings().all()

    returns = db.execute(text("""
        SELECT r.id, r.return_ref, r.requested_at, r.reason, r.refund_amount,
               r.status, p.title AS product_title, p.category
        FROM returns r LEFT JOIN products p ON p.id = r.product_id
        WHERE r.customer_id = :cid ORDER BY r.requested_at DESC LIMIT 50
    """), {"cid": customer_id}).mappings().all()

    sessions = db.execute(text("""
        SELECT cs.id, cs.started_at, cs.cart_value, cs.shipping_cost,
               cs.shipping_cart_ratio, cs.payment_attempts, cs.payment_failed,
               cs.payment_method, cs.device_type, cs.checkout_stage,
               cs.item_count, cs.session_duration_sec, cs.coupon_applied,
               cs.coupon_failed, cs.address_edits, cs.page_errors,
               cs.hour_of_day, cs.is_weekend, cs.abandoned,
               cs.prior_order_count, cs.prior_abandonment_count,
               cs.prior_return_count, cs.prior_rto_count,
               ac.id AS cart_id, ac.primary_reason, ac.recovered
        FROM checkout_sessions cs
        LEFT JOIN abandoned_carts ac ON ac.checkout_session_id = cs.id
        WHERE cs.customer_id = :cid ORDER BY cs.started_at DESC LIMIT 50
    """), {"cid": customer_id}).mappings().all()

    reviews = db.execute(text("""
        SELECT r.id, r.rating, r.review_text, r.review_date, p.title AS product_title,
               ra.sentiment, ra.sentiment_score, ra.priority
        FROM reviews r
        LEFT JOIN products p ON p.id = r.product_id
        LEFT JOIN review_analysis ra ON ra.review_id = r.id
        WHERE r.customer_id = :cid ORDER BY r.review_date DESC LIMIT 25
    """), {"cid": customer_id}).mappings().all()

    aspects = db.execute(text("""
        SELECT a.aspect, a.sentiment, COUNT(*) AS count
        FROM review_aspects a JOIN reviews r ON r.id = a.review_id
        WHERE r.customer_id = :cid GROUP BY a.aspect, a.sentiment
    """), {"cid": customer_id}).mappings().all()

    interventions = db.execute(text("""
        SELECT i.id, i.pillar, i.action, i.channel, i.sent_at,
               i.predicted_probability, i.expected_profit, i.outcome,
               c.revenue, c.realised_profit, c.converted_at
        FROM interventions i LEFT JOIN conversions c ON c.intervention_id = i.id
        WHERE i.customer_id = :cid ORDER BY i.sent_at DESC LIMIT 50
    """), {"cid": customer_id}).mappings().all()

    anomalies = db.execute(text("""
        SELECT anomaly_class, anomaly_score, risk_level, triggered_rules,
               evidence, recommended_action, estimated_exposure, detected_at
        FROM fraud_events WHERE customer_id = :cid ORDER BY detected_at DESC
    """), {"cid": customer_id}).mappings().all()

    orders_n = int(profile["order_count"]) or 0
    return {
        "profile": {
            **dict(profile),
            "total_spend": float(profile["total_spend"]),
            "signup_date": profile["signup_date"].isoformat(),
            "return_rate": round(int(profile["return_count"]) / orders_n, 4)
            if orders_n else 0.0,
            "rto_rate": round(int(profile["rto_count"]) / orders_n, 4)
            if orders_n else 0.0,
            "avg_order_value": round(float(profile["total_spend"]) / orders_n, 2)
            if orders_n else 0.0,
            "value_tier": (
                "HIGH" if float(profile["total_spend"]) >= 60000
                else "MEDIUM" if float(profile["total_spend"]) >= 15000 else "LOW"
            ),
        },
        "orders": [
            {**dict(o), "order_value": float(o["order_value"]),
             "order_date": o["order_date"].isoformat()} for o in orders
        ],
        "payments": [
            {**dict(p), "amount": float(p["amount"]),
             "attempted_at": p["attempted_at"].isoformat()} for p in payments
        ],
        "returns": [
            {**dict(r), "refund_amount": float(r["refund_amount"]),
             "requested_at": r["requested_at"].isoformat()} for r in returns
        ],
        "checkout_sessions": [
            {**dict(s), "cart_value": float(s["cart_value"]),
             "shipping_cost": float(s["shipping_cost"]),
             "shipping_cart_ratio": float(s["shipping_cart_ratio"]),
             "started_at": s["started_at"].isoformat()} for s in sessions
        ],
        "reviews": [
            {**dict(r), "review_date": r["review_date"].isoformat()} for r in reviews
        ],
        "review_aspects": [dict(a) | {"count": int(a["count"])} for a in aspects],
        "interventions": [
            {**dict(i), "sent_at": i["sent_at"].isoformat(),
             "converted_at": i["converted_at"].isoformat() if i["converted_at"] else None,
             "revenue": float(i["revenue"]) if i["revenue"] is not None else None,
             "realised_profit": float(i["realised_profit"])
             if i["realised_profit"] is not None else None,
             "expected_profit": float(i["expected_profit"])}
            for i in interventions
        ],
        "anomalies": [
            {**dict(a), "anomaly_score": float(a["anomaly_score"]),
             "estimated_exposure": float(a["estimated_exposure"]),
             "detected_at": a["detected_at"].isoformat(),
             "triggered_rules": (a["triggered_rules"] or "").split("|")}
            for a in anomalies
        ],
        "disclosure": SYNTHETIC_DATA_DISCLOSURE,
    }


@router.get("/customer/{customer_id}/intelligence")
def customer_intelligence(customer_id: int, db: Session = Depends(get_db)):
    """AI Decision Center: all three risk scores, explanations and the next best action."""
    store, costs = get_store(), get_costs()

    profile = db.execute(text("""
        SELECT id, name, segment, city, order_count, total_spend, return_count,
               rto_count, abandonment_count, delivery_failure_count
        FROM customers WHERE id = :cid
    """), {"cid": customer_id}).mappings().first()
    if profile is None:
        raise HTTPException(status_code=404, detail=f"Customer {customer_id} not found")

    # Most recent abandoned cart drives the recovery half of the view.
    cart = db.execute(text("""
        SELECT ac.id AS cart_id, ac.cart_value, ac.primary_reason, ac.recovered,
               cs.shipping_cost, cs.shipping_cart_ratio, cs.item_count,
               cs.payment_attempts, cs.payment_failed, cs.payment_method,
               cs.device_type, cs.checkout_stage, cs.session_duration_sec,
               cs.coupon_applied, cs.coupon_failed, cs.address_edits,
               cs.page_errors, cs.hour_of_day, cs.is_weekend,
               cs.prior_order_count, cs.prior_abandonment_count,
               cs.prior_return_count, cs.prior_rto_count
        FROM abandoned_carts ac
        JOIN checkout_sessions cs ON cs.id = ac.checkout_session_id
        WHERE ac.customer_id = :cid
        ORDER BY ac.abandoned_at DESC LIMIT 1
    """), {"cid": customer_id}).mappings().first()

    # Most recent order drives the protection half.
    order = db.execute(text("""
        SELECT o.id AS order_id, o.order_value, o.is_cod, o.payment_method,
               oi.product_id, oi.quantity, p.category, p.price AS product_price,
               p.weight_kg, p.has_size_variants, c.city,
               COALESCE(s.courier, 'Delhivery') AS courier,
               COALESCE(s.promised_days, 4) AS promised_days,
               v.review_count AS voc_review_count, p.avg_rating AS voc_avg_rating,
               COALESCE(v.size_fit_complaint_rate, 0)  AS voc_size_fit_rate,
               COALESCE(v.quality_complaint_rate, 0)   AS voc_quality_rate,
               COALESCE(v.delivery_complaint_rate, 0)  AS voc_delivery_rate,
               COALESCE(v.packaging_complaint_rate, 0) AS voc_packaging_rate
        FROM orders o
        JOIN order_items oi ON oi.order_id = o.id
        JOIN products p     ON p.id = oi.product_id
        JOIN customers c    ON c.id = o.customer_id
        LEFT JOIN shipments s ON s.order_id = o.id
        LEFT JOIN product_voc_signals v ON v.product_id = p.id
        WHERE o.customer_id = :cid
        ORDER BY o.order_date DESC LIMIT 1
    """), {"cid": customer_id}).mappings().first()

    result: dict[str, Any] = {
        "customer": {
            **dict(profile), "total_spend": float(profile["total_spend"]),
            "value_tier": (
                "HIGH" if float(profile["total_spend"]) >= 60000
                else "MEDIUM" if float(profile["total_spend"]) >= 15000 else "LOW"
            ),
        },
        "checkout_risk": None,
        "return_risk": None,
        "rto_risk": None,
        "recovery_decision": None,
        "protection_decision": None,
        "anomaly": None,
        "disclosure": SYNTHETIC_DATA_DISCLOSURE,
    }

    if cart is not None:
        session_payload = {
            k: (float(v) if k in ("cart_value", "shipping_cost", "shipping_cart_ratio")
                else v)
            for k, v in dict(cart).items()
        }
        try:
            from ml.recovery import abandonment_model

            result["checkout_risk"] = abandonment_model.predict(session_payload, store)
            decision = decide_recovery(session_payload, store, costs)
            result["recovery_decision"] = decision.to_dict()
            result["abandoned_cart"] = {
                "cart_id": int(cart["cart_id"]),
                "cart_value": float(cart["cart_value"]),
                "primary_reason": cart["primary_reason"],
                "recovered": bool(cart["recovered"]),
            }
        except ModelNotTrained as exc:
            result["checkout_risk"] = {"error": str(exc)}

    voc_signals: list[str] = []
    if order is not None:
        order_payload = {
            k: (float(v) if k in ("order_value", "product_price", "weight_kg",
                                  "voc_avg_rating", "voc_size_fit_rate",
                                  "voc_quality_rate", "voc_delivery_rate",
                                  "voc_packaging_rate")
                else v)
            for k, v in dict(order).items()
        }
        order_payload.update({
            "prior_order_count": int(profile["order_count"]),
            "prior_return_count": int(profile["return_count"]),
            "prior_rto_count": int(profile["rto_count"]),
            "prior_delivery_failures": int(profile["delivery_failure_count"]),
        })
        # Review-derived concerns above 15% become live protection signals.
        for key, signal in (
            ("voc_size_fit_rate", "SIZE_FIT"),
            ("voc_packaging_rate", "PACKAGING"),
            ("voc_delivery_rate", "DELIVERY"),
        ):
            if float(order_payload.get(key) or 0) >= 0.15:
                voc_signals.append(signal)

        try:
            ret = return_model.predict(order_payload, store)
            rto = rto_model.predict(order_payload, store)
            result["return_risk"] = ret
            result["rto_risk"] = rto
            result["protection_decision"] = decide_protection(
                order={"order_value": order_payload["order_value"],
                       "is_cod": order_payload["is_cod"]},
                rto_probability=rto["rto_probability"],
                return_probability=ret["return_probability"],
                costs=costs, voc_signals=voc_signals,
            ).to_dict()
            result["voc_signals"] = voc_signals
        except ModelNotTrained as exc:
            result["return_risk"] = {"error": str(exc)}

    orders_n = int(profile["order_count"]) or 0
    anomaly_payload = {
        "order_count": orders_n,
        "total_spend": float(profile["total_spend"]),
        "return_count": int(profile["return_count"]),
        "rto_count": int(profile["rto_count"]),
        "shipment_count": orders_n,
        "delivery_failure_count": int(profile["delivery_failure_count"]),
        "return_rate": (int(profile["return_count"]) / orders_n) if orders_n else 0.0,
        "rto_rate": (int(profile["rto_count"]) / orders_n) if orders_n else 0.0,
        "avg_order_value": (float(profile["total_spend"]) / orders_n) if orders_n else 0.0,
    }
    result["anomaly"] = fraud_model.analyze(anomaly_payload, store).to_dict()
    return result
