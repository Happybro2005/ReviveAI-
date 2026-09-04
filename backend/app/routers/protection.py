"""PROTECT pillar endpoints: returns, RTO, anomalies."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from ml.common import ModelNotTrained
from ml.decision.decision_engine import decide_protection
from ml.protection import fraud_model, return_model, rto_model

from ..config import SYNTHETIC_DATA_DISCLOSURE
from ..db import get_db
from ..deps import get_costs, get_store
from ..schemas import (
    AnomalyInput,
    ProtectionDecisionInput,
    ReturnRiskInput,
    RTORiskInput,
)

router = APIRouter(tags=["protection"])


def _voc_for_product(db: Session, product_id: int | None) -> dict[str, Any] | None:
    """Look up stored review signals so callers need not supply them."""
    if product_id is None:
        return None
    row = db.execute(text("""
        SELECT s.review_count, s.negative_share, s.size_fit_complaint_rate,
               s.quality_complaint_rate, s.delivery_complaint_rate,
               s.packaging_complaint_rate, p.avg_rating, p.title, p.category
        FROM product_voc_signals s
        JOIN products p ON p.id = s.product_id
        WHERE s.product_id = :pid
    """), {"pid": product_id}).mappings().first()
    return dict(row) if row else None


@router.get("/protection/overview")
def overview(db: Session = Depends(get_db), days: int = Query(default=180, ge=1, le=1095)):
    """Protection KPIs computed from orders, shipments, returns and anomalies."""
    ship = db.execute(text("""
        SELECT COUNT(*) AS shipments,
               COUNT(*) FILTER (WHERE is_rto) AS rto,
               COUNT(*) FILTER (WHERE status = 'DELIVERED') AS delivered,
               COALESCE(AVG(actual_days) FILTER (WHERE actual_days IS NOT NULL), 0) AS avg_days,
               COUNT(*) FILTER (WHERE actual_days > promised_days) AS late
        FROM shipments
        WHERE shipped_at >= NOW() - make_interval(days => :days)
    """), {"days": days}).mappings().one()

    ret = db.execute(text("""
        SELECT COUNT(*) AS returns,
               COALESCE(SUM(refund_amount), 0) AS refund_value
        FROM returns
        WHERE requested_at >= NOW() - make_interval(days => :days)
    """), {"days": days}).mappings().one()

    orders = db.execute(text("""
        SELECT COUNT(*) AS orders, COALESCE(SUM(order_value), 0) AS value,
               COUNT(*) FILTER (WHERE is_cod) AS cod_orders
        FROM orders
        WHERE order_date >= NOW() - make_interval(days => :days)
    """), {"days": days}).mappings().one()

    reasons = db.execute(text("""
        SELECT reason, COUNT(*) AS count, COALESCE(SUM(refund_amount), 0) AS value
        FROM returns
        WHERE requested_at >= NOW() - make_interval(days => :days)
        GROUP BY reason ORDER BY count DESC
    """), {"days": days}).mappings().all()

    rto_reasons = db.execute(text("""
        SELECT COALESCE(rto_reason, 'UNKNOWN') AS reason, COUNT(*) AS count
        FROM shipments
        WHERE is_rto AND shipped_at >= NOW() - make_interval(days => :days)
        GROUP BY 1 ORDER BY count DESC
    """), {"days": days}).mappings().all()

    couriers = db.execute(text("""
        SELECT courier, COUNT(*) AS shipments,
               COUNT(*) FILTER (WHERE is_rto) AS rto,
               COUNT(*) FILTER (WHERE actual_days > promised_days) AS late,
               COALESCE(AVG(actual_days) FILTER (WHERE actual_days IS NOT NULL), 0) AS avg_days
        FROM shipments
        WHERE shipped_at >= NOW() - make_interval(days => :days)
        GROUP BY courier ORDER BY shipments DESC
    """), {"days": days}).mappings().all()

    anomalies = db.execute(text("""
        SELECT anomaly_class, risk_level, COUNT(*) AS count,
               COALESCE(SUM(estimated_exposure), 0) AS exposure
        FROM fraud_events
        GROUP BY anomaly_class, risk_level ORDER BY count DESC
    """)).mappings().all()

    costs = get_costs()
    n_rto, n_ret = int(ship["rto"]), int(ret["returns"])
    aov = float(orders["value"]) / int(orders["orders"]) if orders["orders"] else 0.0

    return {
        "window_days": days,
        "orders": int(orders["orders"]),
        "order_value": float(orders["value"]),
        "cod_share": (
            round(int(orders["cod_orders"]) / int(orders["orders"]), 4)
            if orders["orders"] else 0.0
        ),
        "shipments": int(ship["shipments"]),
        "delivered": int(ship["delivered"]),
        "rto_count": n_rto,
        "rto_rate": (
            round(n_rto / int(ship["shipments"]), 4) if ship["shipments"] else 0.0
        ),
        "late_deliveries": int(ship["late"]),
        "avg_delivery_days": round(float(ship["avg_days"]), 2),
        "returns": n_ret,
        "return_rate": (
            round(n_ret / int(orders["orders"]), 4) if orders["orders"] else 0.0
        ),
        "refund_value": float(ret["refund_value"]),
        "rto_loss": round(n_rto * costs.rto_loss(), 2),
        "return_loss": round(n_ret * costs.return_loss(aov), 2),
        "loss_basis": (
            f"RTO loss = {n_rto} x Rs {costs.rto_loss():,.0f} per event. "
            f"Return loss = {n_ret} x Rs {costs.return_loss(aov):,.0f} per event "
            f"at an average order value of Rs {aov:,.0f}. Observed losses in the "
            f"window, not forecasts."
        ),
        "return_reasons": [
            {"reason": r["reason"], "count": int(r["count"]), "value": float(r["value"])}
            for r in reasons
        ],
        "rto_reasons": [
            {"reason": r["reason"], "count": int(r["count"])} for r in rto_reasons
        ],
        "couriers": [
            {
                "courier": c["courier"], "shipments": int(c["shipments"]),
                "rto": int(c["rto"]),
                "rto_rate": round(int(c["rto"]) / int(c["shipments"]), 4)
                if c["shipments"] else 0.0,
                "late": int(c["late"]), "avg_days": round(float(c["avg_days"]), 2),
            }
            for c in couriers
        ],
        "anomalies": [
            {
                "anomaly_class": a["anomaly_class"], "risk_level": a["risk_level"],
                "count": int(a["count"]), "exposure": float(a["exposure"]),
            }
            for a in anomalies
        ],
        "disclosure": SYNTHETIC_DATA_DISCLOSURE,
    }


@router.post("/returns/predict")
def predict_return(body: ReturnRiskInput, db: Session = Depends(get_db)):
    store = get_store()
    payload = body.model_dump()

    # Prefer stored review signals over caller-supplied ones when a product is named.
    voc = _voc_for_product(db, body.product_id)
    if voc:
        payload.update({
            "voc_review_count": float(voc["review_count"]),
            "voc_avg_rating": float(voc["avg_rating"] or 0.0),
            "voc_size_fit_rate": float(voc["size_fit_complaint_rate"]),
            "voc_quality_rate": float(voc["quality_complaint_rate"]),
            "voc_delivery_rate": float(voc["delivery_complaint_rate"]),
            "voc_packaging_rate": float(voc["packaging_complaint_rate"]),
        })
    try:
        result = return_model.predict(payload, store)
    except ModelNotTrained as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    result["voc_context"] = (
        {
            "product_title": voc["title"], "category": voc["category"],
            "review_count": int(voc["review_count"]),
            "size_fit_complaint_rate": round(float(voc["size_fit_complaint_rate"]), 4),
            "quality_complaint_rate": round(float(voc["quality_complaint_rate"]), 4),
            "note": (
                "Review-derived complaint rates for this product are model inputs, "
                "so customer feedback influences this score directly."
            ),
        }
        if voc else None
    )
    result["disclosure"] = SYNTHETIC_DATA_DISCLOSURE
    return result


@router.post("/rto/predict")
def predict_rto(body: RTORiskInput):
    store = get_store()
    try:
        result = rto_model.predict(body.model_dump(), store)
    except ModelNotTrained as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    result["disclosure"] = SYNTHETIC_DATA_DISCLOSURE
    return result


@router.post("/fraud/analyze")
def analyze_anomaly(body: AnomalyInput, db: Session = Depends(get_db)):
    """Hybrid rules + IsolationForest anomaly analysis."""
    store = get_store()
    payload = body.model_dump()

    # Fill behavioural aggregates from the database when a customer is named.
    if body.customer_id is not None:
        row = db.execute(text("""
            SELECT c.order_count, c.total_spend, c.return_count, c.rto_count,
                   c.delivery_failure_count, c.cod_refusal_count,
                   (SELECT COUNT(*) FROM shipments s WHERE s.customer_id = c.id) AS shipment_count,
                   (SELECT COUNT(*) FROM orders o WHERE o.customer_id = c.id AND o.is_cod) AS cod_orders,
                   (SELECT MIN(order_date) FROM orders o WHERE o.customer_id = c.id) AS first_order,
                   (SELECT MAX(order_date) FROM orders o WHERE o.customer_id = c.id) AS last_order
            FROM customers c WHERE c.id = :cid
        """), {"cid": body.customer_id}).mappings().first()
        if row is None:
            raise HTTPException(
                status_code=404, detail=f"Customer {body.customer_id} not found"
            )
        orders = int(row["order_count"]) or 0
        spend = float(row["total_spend"] or 0)
        span = 1
        if row["first_order"] and row["last_order"]:
            span = max((row["last_order"] - row["first_order"]).days, 1)
        payload.update({
            "order_count": orders, "total_spend": spend,
            "return_count": int(row["return_count"]),
            "rto_count": int(row["rto_count"]),
            "shipment_count": int(row["shipment_count"]),
            "cod_refusal_count": int(row["cod_refusal_count"]),
            "delivery_failure_count": int(row["delivery_failure_count"]),
            "return_rate": (int(row["return_count"]) / orders) if orders else 0.0,
            "rto_rate": (int(row["rto_count"]) / orders) if orders else 0.0,
            "cod_share": (int(row["cod_orders"]) / orders) if orders else 0.0,
            "avg_order_value": (spend / orders) if orders else 0.0,
            "orders_per_active_day": orders / span,
        })

    result = fraud_model.analyze(payload, store).to_dict()
    result["disclosure"] = SYNTHETIC_DATA_DISCLOSURE
    return result


@router.post("/protection/decision")
def protection_decision(body: ProtectionDecisionInput):
    """Compare protection actions and return the next best one."""
    costs = get_costs()
    result = decide_protection(
        order={"order_value": body.order_value, "is_cod": body.is_cod},
        rto_probability=body.rto_probability,
        return_probability=body.return_probability,
        costs=costs,
        voc_signals=body.voc_signals,
    )
    return result.to_dict()


@router.get("/protection/anomalies")
def list_anomalies(
    db: Session = Depends(get_db),
    limit: int = Query(default=25, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    anomaly_class: str | None = None,
):
    where, params = [], {"limit": limit, "offset": offset}
    if anomaly_class:
        where.append("f.anomaly_class = :cls")
        params["cls"] = anomaly_class
    clause = (" WHERE " + " AND ".join(where)) if where else ""

    total = db.execute(
        text(f"SELECT COUNT(*) FROM fraud_events f{clause}"), params
    ).scalar_one()
    rows = db.execute(text(f"""
        SELECT f.id, f.customer_id, f.order_id, f.shipment_id, f.detected_at,
               f.anomaly_class, f.anomaly_score, f.risk_level, f.triggered_rules,
               f.evidence, f.recommended_action, f.estimated_exposure,
               c.name AS customer_name, c.segment
        FROM fraud_events f
        LEFT JOIN customers c ON c.id = f.customer_id
        {clause}
        ORDER BY f.anomaly_score DESC, f.detected_at DESC
        LIMIT :limit OFFSET :offset
    """), params).mappings().all()

    return {
        "items": [
            {
                "id": int(r["id"]), "customer_id": r["customer_id"],
                "customer_name": r["customer_name"], "segment": r["segment"],
                "order_id": r["order_id"], "shipment_id": r["shipment_id"],
                "detected_at": r["detected_at"].isoformat(),
                "anomaly_class": r["anomaly_class"],
                "anomaly_score": float(r["anomaly_score"]),
                "risk_level": r["risk_level"],
                "triggered_rules": (r["triggered_rules"] or "").split("|"),
                "evidence": r["evidence"],
                "recommended_action": r["recommended_action"],
                "estimated_exposure": float(r["estimated_exposure"]),
            }
            for r in rows
        ],
        "total": int(total), "limit": limit, "offset": offset,
        "note": (
            "Anomalies are review prompts, not fraud determinations. "
            "CUSTOMER_BEHAVIOR and LOGISTICS_OPERATIONAL are reported separately."
        ),
        "disclosure": SYNTHETIC_DATA_DISCLOSURE,
    }
