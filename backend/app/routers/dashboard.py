"""Unified dashboard: one view across all three pillars, all database-driven."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from ml.nlp.lexicon import ASPECT_LABELS, ASPECT_RISK_SIGNAL

from ..config import SYNTHETIC_DATA_DISCLOSURE
from ..db import get_db
from ..deps import get_costs

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db),
              days: int = Query(default=180, ge=1, le=1095)):
    costs = get_costs()
    p = {"days": days}

    recovery = db.execute(text("""
        SELECT
          (SELECT COUNT(*) FROM checkout_sessions
             WHERE started_at >= NOW() - make_interval(days => :days)) AS sessions,
          (SELECT COUNT(*) FROM checkout_sessions
             WHERE abandoned AND started_at >= NOW() - make_interval(days => :days)) AS abandoned,
          (SELECT COALESCE(SUM(cart_value), 0) FROM abandoned_carts
             WHERE abandoned_at >= NOW() - make_interval(days => :days)) AS revenue_at_risk,
          (SELECT COALESCE(SUM(recovered_revenue), 0) FROM abandoned_carts
             WHERE recovered AND abandoned_at >= NOW() - make_interval(days => :days)) AS recovered_revenue,
          (SELECT COUNT(*) FROM abandoned_carts
             WHERE recovered AND abandoned_at >= NOW() - make_interval(days => :days)) AS recovered_carts,
          (SELECT COUNT(*) FROM abandoned_carts
             WHERE abandoned_at >= NOW() - make_interval(days => :days)) AS total_carts,
          (SELECT COALESCE(SUM(realised_profit), 0) FROM conversions
             WHERE converted_at >= NOW() - make_interval(days => :days)) AS incremental_profit
    """), p).mappings().one()

    protection = db.execute(text("""
        SELECT
          (SELECT COUNT(*) FROM shipments
             WHERE shipped_at >= NOW() - make_interval(days => :days)) AS shipments,
          (SELECT COUNT(*) FROM shipments
             WHERE is_rto AND shipped_at >= NOW() - make_interval(days => :days)) AS rto,
          (SELECT COUNT(*) FROM returns
             WHERE requested_at >= NOW() - make_interval(days => :days)) AS returns,
          (SELECT COUNT(*) FROM orders
             WHERE order_date >= NOW() - make_interval(days => :days)) AS orders,
          (SELECT COALESCE(AVG(order_value), 0) FROM orders
             WHERE order_date >= NOW() - make_interval(days => :days)) AS aov,
          (SELECT COALESCE(SUM(estimated_exposure), 0) FROM fraud_events
             WHERE anomaly_class = 'CUSTOMER_BEHAVIOR') AS anomaly_exposure,
          (SELECT COUNT(*) FROM fraud_events) AS anomaly_count
    """), p).mappings().one()

    voc = db.execute(text("""
        SELECT
          (SELECT COUNT(*) FROM reviews) AS total_reviews,
          (SELECT COUNT(*) FROM review_analysis) AS analysed,
          (SELECT COALESCE(AVG(rating), 0) FROM reviews) AS avg_rating
    """)).mappings().one()

    sentiment = db.execute(text(
        "SELECT sentiment, COUNT(*) AS count FROM review_analysis GROUP BY sentiment"
    )).mappings().all()

    concerns = db.execute(text("""
        SELECT aspect, COUNT(*) FILTER (WHERE sentiment = 'NEGATIVE') AS negative,
               COUNT(*) AS total
        FROM review_aspects GROUP BY aspect
        HAVING COUNT(*) FILTER (WHERE sentiment = 'NEGATIVE') > 0
        ORDER BY negative DESC LIMIT 8
    """)).mappings().all()

    leakage_trend = db.execute(text("""
        SELECT date_trunc('month', started_at)::date AS month,
               COALESCE(SUM(cart_value) FILTER (WHERE abandoned), 0) AS abandoned_value,
               COALESCE(SUM(cart_value) FILTER (WHERE NOT abandoned), 0) AS completed_value
        FROM checkout_sessions
        WHERE started_at >= NOW() - make_interval(days => :days)
        GROUP BY 1 ORDER BY 1
    """), p).mappings().all()

    funnel = db.execute(text("""
        SELECT
          (SELECT COUNT(*) FROM checkout_sessions
             WHERE started_at >= NOW() - make_interval(days => :days)) AS started,
          (SELECT COUNT(*) FROM checkout_sessions
             WHERE abandoned AND started_at >= NOW() - make_interval(days => :days)) AS abandoned,
          (SELECT COUNT(*) FROM interventions
             WHERE pillar = 'RECOVERY'
               AND sent_at >= NOW() - make_interval(days => :days)) AS contacted,
          (SELECT COUNT(*) FROM conversions
             WHERE converted_at >= NOW() - make_interval(days => :days)) AS converted
    """), p).mappings().one()

    recs = db.execute(text("""
        SELECT aspect, priority, problem, recommendation,
               supporting_review_count, estimated_business_impact, linked_risk_signal
        FROM seller_recommendations
        ORDER BY CASE priority WHEN 'CRITICAL' THEN 0 WHEN 'HIGH' THEN 1
                               WHEN 'MEDIUM' THEN 2 ELSE 3 END,
                 estimated_business_impact DESC
        LIMIT 5
    """)).mappings().all()

    n_rto = int(protection["rto"])
    n_ret = int(protection["returns"])
    aov = float(protection["aov"] or 0)
    rto_loss = n_rto * costs.rto_loss()
    return_loss = n_ret * costs.return_loss(aov)
    total_carts = int(recovery["total_carts"])

    return {
        "window_days": days,
        "kpis": {
            "revenue_recovered": float(recovery["recovered_revenue"]),
            "revenue_at_risk": float(recovery["revenue_at_risk"]),
            "incremental_profit": float(recovery["incremental_profit"]),
            "recovery_rate": round(int(recovery["recovered_carts"]) / total_carts, 4)
            if total_carts else 0.0,
            "abandonment_rate": round(
                int(recovery["abandoned"]) / int(recovery["sessions"]), 4
            ) if recovery["sessions"] else 0.0,
            "revenue_leaking_to_rto": round(rto_loss, 2),
            "revenue_leaking_to_returns": round(return_loss, 2),
            "revenue_protected_opportunity": round(rto_loss + return_loss, 2),
            "rto_count": n_rto,
            "return_count": n_ret,
            "rto_rate": round(n_rto / int(protection["shipments"]), 4)
            if protection["shipments"] else 0.0,
            "return_rate": round(n_ret / int(protection["orders"]), 4)
            if protection["orders"] else 0.0,
            "anomaly_exposure": float(protection["anomaly_exposure"]),
            "anomaly_count": int(protection["anomaly_count"]),
            "total_reviews": int(voc["total_reviews"]),
            "analysed_reviews": int(voc["analysed"]),
            "average_rating": round(float(voc["avg_rating"]), 2),
        },
        "kpi_basis": (
            "Revenue recovered and incremental profit are summed from recorded "
            "conversions. RTO and return leakage are observed event counts priced "
            "with the published cost model, not forecasts."
        ),
        "revenue_leakage": [
            {
                "month": str(r["month"]),
                "abandoned_value": float(r["abandoned_value"]),
                "completed_value": float(r["completed_value"]),
            }
            for r in leakage_trend
        ],
        "recovery_funnel": [
            {"stage": "Checkouts started", "count": int(funnel["started"])},
            {"stage": "Abandoned", "count": int(funnel["abandoned"])},
            {"stage": "Contacted", "count": int(funnel["contacted"])},
            {"stage": "Recovered", "count": int(funnel["converted"])},
        ],
        "sentiment_distribution": {
            s["sentiment"]: int(s["count"]) for s in sentiment
        },
        "top_concerns": [
            {
                "aspect": c["aspect"],
                "aspect_label": ASPECT_LABELS.get(c["aspect"], c["aspect"]),
                "negative_mentions": int(c["negative"]),
                "total_mentions": int(c["total"]),
                "negative_share": round(int(c["negative"]) / int(c["total"]), 4)
                if c["total"] else 0.0,
                "risk_signal": ASPECT_RISK_SIGNAL.get(c["aspect"]),
            }
            for c in concerns
        ],
        "recommendations": [
            {
                "aspect": r["aspect"],
                "aspect_label": ASPECT_LABELS.get(r["aspect"], r["aspect"]),
                "priority": r["priority"], "problem": r["problem"],
                "recommendation": r["recommendation"],
                "supporting_review_count": int(r["supporting_review_count"]),
                "estimated_business_impact": float(r["estimated_business_impact"]),
                "linked_risk_signal": r["linked_risk_signal"],
            }
            for r in recs
        ],
        "disclosure": SYNTHETIC_DATA_DISCLOSURE,
    }
