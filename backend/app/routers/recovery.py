"""RECOVER pillar endpoints."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from ml.common import ModelNotTrained
from ml.decision.decision_engine import decide_recovery
from ml.recovery import abandonment_model, recovery_model
from ml.recovery.reason_engine import diagnose

from ..config import SYNTHETIC_DATA_DISCLOSURE
from ..db import get_db
from ..deps import get_costs, get_store
from ..schemas import CheckoutSessionInput, DecisionResponse, InterventionCreate

router = APIRouter(prefix="/recovery", tags=["recovery"])


def _payload(session: CheckoutSessionInput) -> dict[str, Any]:
    data = session.model_dump()
    data["shipping_cart_ratio"] = session.shipping_cart_ratio
    return data


@router.get("/overview")
def overview(db: Session = Depends(get_db), days: int = Query(default=180, ge=1, le=1095)):
    """Recovery funnel and revenue figures, computed from the database."""
    row = db.execute(text("""
        SELECT
          COUNT(*)                                             AS sessions,
          COUNT(*) FILTER (WHERE abandoned)                    AS abandoned,
          COALESCE(SUM(cart_value) FILTER (WHERE abandoned), 0) AS revenue_at_risk,
          COALESCE(SUM(cart_value) FILTER (WHERE NOT abandoned), 0) AS completed_revenue
        FROM checkout_sessions
        WHERE started_at >= NOW() - make_interval(days => :days)
    """), {"days": days}).mappings().one()

    rec = db.execute(text("""
        SELECT COUNT(*) AS carts,
               COUNT(*) FILTER (WHERE recovered) AS recovered,
               COALESCE(SUM(recovered_revenue), 0) AS recovered_revenue
        FROM abandoned_carts
        WHERE abandoned_at >= NOW() - make_interval(days => :days)
    """), {"days": days}).mappings().one()

    reasons = db.execute(text("""
        SELECT primary_reason AS reason, COUNT(*) AS count,
               COALESCE(SUM(cart_value), 0) AS value,
               COUNT(*) FILTER (WHERE recovered) AS recovered
        FROM abandoned_carts
        WHERE abandoned_at >= NOW() - make_interval(days => :days)
        GROUP BY primary_reason ORDER BY count DESC
    """), {"days": days}).mappings().all()

    actions = db.execute(text("""
        SELECT i.action, COUNT(*) AS sent,
               COUNT(*) FILTER (WHERE i.outcome = 'CONVERTED') AS converted,
               COALESCE(SUM(c.revenue), 0) AS revenue,
               COALESCE(SUM(c.realised_profit), 0) AS profit
        FROM interventions i
        LEFT JOIN conversions c ON c.intervention_id = i.id
        WHERE i.pillar = 'RECOVERY'
          AND i.sent_at >= NOW() - make_interval(days => :days)
        GROUP BY i.action ORDER BY sent DESC
    """), {"days": days}).mappings().all()

    trend = db.execute(text("""
        SELECT date_trunc('week', abandoned_at)::date AS week,
               COUNT(*) AS abandoned,
               COUNT(*) FILTER (WHERE recovered) AS recovered,
               COALESCE(SUM(cart_value), 0) AS at_risk,
               COALESCE(SUM(recovered_revenue), 0) AS recovered_revenue
        FROM abandoned_carts
        WHERE abandoned_at >= NOW() - make_interval(days => :days)
        GROUP BY 1 ORDER BY 1
    """), {"days": days}).mappings().all()

    carts = int(rec["carts"]) or 0
    return {
        "window_days": days,
        "sessions": int(row["sessions"]),
        "abandoned": int(row["abandoned"]),
        "abandonment_rate": (
            round(int(row["abandoned"]) / int(row["sessions"]), 4)
            if row["sessions"] else 0.0
        ),
        "revenue_at_risk": float(row["revenue_at_risk"]),
        "completed_revenue": float(row["completed_revenue"]),
        "carts": carts,
        "recovered": int(rec["recovered"]),
        "recovery_rate": round(int(rec["recovered"]) / carts, 4) if carts else 0.0,
        "recovered_revenue": float(rec["recovered_revenue"]),
        "by_reason": [
            {
                "reason": r["reason"], "count": int(r["count"]),
                "value": float(r["value"]), "recovered": int(r["recovered"]),
                "recovery_rate": (
                    round(int(r["recovered"]) / int(r["count"]), 4)
                    if r["count"] else 0.0
                ),
            }
            for r in reasons
        ],
        "by_action": [
            {
                "action": a["action"], "sent": int(a["sent"]),
                "converted": int(a["converted"]),
                "conversion_rate": (
                    round(int(a["converted"]) / int(a["sent"]), 4) if a["sent"] else 0.0
                ),
                "revenue": float(a["revenue"]), "profit": float(a["profit"]),
            }
            for a in actions
        ],
        "trend": [
            {
                "week": str(t["week"]), "abandoned": int(t["abandoned"]),
                "recovered": int(t["recovered"]), "at_risk": float(t["at_risk"]),
                "recovered_revenue": float(t["recovered_revenue"]),
            }
            for t in trend
        ],
        "disclosure": SYNTHETIC_DATA_DISCLOSURE,
    }


@router.post("/predict")
def predict(session: CheckoutSessionInput):
    """Abandonment risk + explanation + diagnosed reason + recovery outlook."""
    store = get_store()
    data = _payload(session)
    try:
        abandonment = abandonment_model.predict(data, store)
        probabilities = recovery_model.predict_all_actions(data, store)
    except ModelNotTrained as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    baseline = probabilities.get("NO_ACTION", 0.0)
    best = max(probabilities.values()) if probabilities else 0.0

    return {
        "abandonment": abandonment,
        "reason": diagnose(data).to_dict(),
        "recovery_probability_baseline": round(baseline, 4),
        "recovery_probability_best_action": round(best, 4),
        "recovery_by_action": {k: round(v, 4) for k, v in probabilities.items()},
        "disclosure": SYNTHETIC_DATA_DISCLOSURE,
    }


@router.post("/decision", response_model=DecisionResponse)
def decision(session: CheckoutSessionInput):
    """Compare every recovery action and return the next best action."""
    store, costs = get_store(), get_costs()
    try:
        result = decide_recovery(_payload(session), store, costs)
    except ModelNotTrained as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return result.to_dict()


@router.post("/intervention", status_code=201)
def create_intervention(body: InterventionCreate, db: Session = Depends(get_db)):
    """Record a dispatched intervention so its outcome can be tracked."""
    exists = db.execute(
        text("SELECT 1 FROM customers WHERE id = :id"), {"id": body.customer_id}
    ).scalar()
    if not exists:
        raise HTTPException(status_code=404, detail=f"Customer {body.customer_id} not found")

    if body.abandoned_cart_id is not None:
        cart = db.execute(
            text("SELECT 1 FROM abandoned_carts WHERE id = :id"),
            {"id": body.abandoned_cart_id},
        ).scalar()
        if not cart:
            raise HTTPException(
                status_code=404,
                detail=f"Abandoned cart {body.abandoned_cart_id} not found",
            )

    now = datetime.now(timezone.utc)
    new_id = db.execute(text("""
        INSERT INTO interventions
            (abandoned_cart_id, order_id, customer_id, pillar, action, channel,
             sent_at, predicted_probability, expected_revenue, intervention_cost,
             discount_cost, expected_profit, model_version, outcome,
             created_at, updated_at)
        VALUES
            (:cart, :order, :customer, :pillar, :action, :channel, :sent_at,
             :prob, :revenue, :cost, :discount, :profit, :version, 'PENDING',
             :now, :now)
        RETURNING id
    """), {
        "cart": body.abandoned_cart_id, "order": body.order_id,
        "customer": body.customer_id, "pillar": body.pillar, "action": body.action,
        "channel": body.channel, "sent_at": now, "prob": body.predicted_probability,
        "revenue": body.expected_revenue, "cost": body.intervention_cost,
        "discount": body.discount_cost, "profit": body.expected_profit,
        "version": body.model_version, "now": now,
    }).scalar_one()
    db.commit()

    return {
        "id": int(new_id), "customer_id": body.customer_id, "pillar": body.pillar,
        "action": body.action, "channel": body.channel, "sent_at": now.isoformat(),
        "predicted_probability": body.predicted_probability,
        "expected_profit": body.expected_profit, "outcome": "PENDING",
    }


@router.get("/carts")
def abandoned_carts(
    db: Session = Depends(get_db),
    limit: int = Query(default=25, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    reason: str | None = None,
    min_value: float = Query(default=0, ge=0),
    recovered: bool | None = None,
):
    """Paginated abandoned carts for the recovery worklist."""
    where = ["ac.cart_value >= :min_value"]
    params: dict[str, Any] = {"min_value": min_value, "limit": limit, "offset": offset}
    if reason:
        where.append("ac.primary_reason = :reason")
        params["reason"] = reason
    if recovered is not None:
        where.append("ac.recovered = :recovered")
        params["recovered"] = recovered
    clause = " AND ".join(where)

    total = db.execute(
        text(f"SELECT COUNT(*) FROM abandoned_carts ac WHERE {clause}"), params
    ).scalar_one()

    rows = db.execute(text(f"""
        SELECT ac.id, ac.customer_id, ac.abandoned_at, ac.cart_value,
               ac.primary_reason, ac.recovered, ac.recovered_revenue,
               c.name AS customer_name, c.segment, c.city,
               cs.id AS session_id, cs.shipping_cost, cs.shipping_cart_ratio,
               cs.payment_attempts, cs.payment_failed, cs.payment_method,
               cs.device_type, cs.checkout_stage, cs.item_count,
               cs.session_duration_sec, cs.coupon_applied, cs.coupon_failed,
               cs.address_edits, cs.page_errors, cs.hour_of_day, cs.is_weekend,
               cs.prior_order_count, cs.prior_abandonment_count,
               cs.prior_return_count, cs.prior_rto_count
        FROM abandoned_carts ac
        JOIN customers c        ON c.id = ac.customer_id
        JOIN checkout_sessions cs ON cs.id = ac.checkout_session_id
        WHERE {clause}
        ORDER BY ac.cart_value DESC, ac.abandoned_at DESC
        LIMIT :limit OFFSET :offset
    """), params).mappings().all()

    return {
        "items": [
            {**{k: (float(v) if k in ("cart_value", "recovered_revenue",
                                      "shipping_cost", "shipping_cart_ratio")
                    else v.isoformat() if k == "abandoned_at" else v)
                for k, v in dict(r).items()}}
            for r in rows
        ],
        "total": int(total), "limit": limit, "offset": offset,
        "disclosure": SYNTHETIC_DATA_DISCLOSURE,
    }
