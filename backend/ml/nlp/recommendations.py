"""Seller recommendation engine.

Turns aggregated review evidence into ranked business actions. Two rules govern
this module:

1. Nothing is recommended without counted evidence. Every card carries the
   number of reviews behind it and the negative share those reviews represent.
2. Business impact is *observed*, not forecast. The rupee figure attached to a
   recommendation is the loss already present in the database that the fix
   addresses -- returns with a matching reason, RTOs on complained-about lanes --
   priced with the same cost model the decision engine uses. It is labelled with
   the exact calculation in `impact_basis`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..decision.economics import CostModel
from .lexicon import ASPECT_LABELS, ASPECT_RECOMMENDATION, ASPECT_RISK_SIGNAL

# Minimum evidence before an aspect becomes a recommendation.
MIN_REVIEWS_PRODUCT = 8
MIN_REVIEWS_CATEGORY = 40
MIN_NEGATIVE_SHARE = 0.20

# Which return reasons a given aspect complaint is responsible for.
_ASPECT_TO_RETURN_REASONS: dict[str, tuple[str, ...]] = {
    "SIZE_FIT": ("SIZE_FIT",),
    "PRODUCT_QUALITY": ("QUALITY_ISSUE", "NOT_AS_DESCRIBED"),
    "PACKAGING": ("DAMAGED_IN_TRANSIT",),
    "DELIVERY": ("LATE_DELIVERY",),
}


@dataclass
class Recommendation:
    scope: str                      # GLOBAL / CATEGORY / PRODUCT
    aspect: str
    problem: str
    recommendation: str
    priority: str
    supporting_review_count: int
    negative_share: float
    evidence: dict[str, Any]
    estimated_business_impact: float
    impact_basis: str
    linked_risk_signal: str | None
    category: str | None = None
    product_id: int | None = None
    product_title: str | None = None
    affected: str = ""
    alternatives: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "scope": self.scope,
            "aspect": self.aspect,
            "aspect_label": ASPECT_LABELS.get(self.aspect, self.aspect),
            "problem": self.problem,
            "recommendation": self.recommendation,
            "priority": self.priority,
            "supporting_review_count": self.supporting_review_count,
            "negative_share": round(self.negative_share, 4),
            "evidence": self.evidence,
            "estimated_business_impact": round(self.estimated_business_impact, 2),
            "impact_basis": self.impact_basis,
            "linked_risk_signal": self.linked_risk_signal,
            "category": self.category,
            "product_id": self.product_id,
            "product_title": self.product_title,
            "affected": self.affected,
        }


def _priority(negative_share: float, count: int, impact: float) -> str:
    score = 0
    if negative_share >= 0.50:
        score += 3
    elif negative_share >= 0.35:
        score += 2
    elif negative_share >= MIN_NEGATIVE_SHARE:
        score += 1
    if count >= 200:
        score += 2
    elif count >= 50:
        score += 1
    if impact >= 100_000:
        score += 2
    elif impact >= 20_000:
        score += 1

    if score >= 6:
        return "CRITICAL"
    if score >= 4:
        return "HIGH"
    if score >= 2:
        return "MEDIUM"
    return "LOW"


def _observed_return_loss(
    session: Session, aspect: str, costs: CostModel,
    product_id: int | None = None, category: str | None = None,
) -> tuple[float, int, str]:
    """Rupee loss already incurred from returns whose reason matches this aspect."""
    reasons = _ASPECT_TO_RETURN_REASONS.get(aspect)
    if not reasons:
        return 0.0, 0, "No return reason maps to this aspect."

    where = ["r.reason = ANY(:reasons)"]
    params: dict[str, Any] = {"reasons": list(reasons)}
    if product_id is not None:
        where.append("r.product_id = :pid")
        params["pid"] = product_id
    if category is not None:
        where.append("p.category = :cat")
        params["cat"] = category

    sql = text(
        "SELECT COUNT(*) AS n, COALESCE(AVG(o.order_value), 0) AS aov "
        "FROM returns r "
        "JOIN products p ON p.id = r.product_id "
        "JOIN orders o   ON o.id = r.order_id "
        "WHERE " + " AND ".join(where)
    )
    row = session.execute(sql, params).mappings().one()
    n = int(row["n"])
    aov = float(row["aov"] or 0.0)
    if n == 0:
        return 0.0, 0, "No matching returns recorded in the data window."

    per_return = costs.return_loss(aov)
    total = n * per_return
    basis = (
        f"{n} returns with reason {'/'.join(reasons)} on an average order value of "
        f"Rs {aov:,.0f}. Loss per return = reverse logistics Rs "
        f"{costs.return_logistics_loss:,.0f} + restocking Rs "
        f"{costs.return_restock_loss:,.0f} + {costs.return_margin_erosion:.0%} "
        f"margin erosion = Rs {per_return:,.0f}. Observed loss in the data "
        f"window, not a forecast."
    )
    return total, n, basis


def _observed_rto_loss(
    session: Session, costs: CostModel, category: str | None = None
) -> tuple[float, int, str]:
    """Rupee loss from RTOs, used for delivery/logistics complaints."""
    where = ["s.is_rto = TRUE"]
    params: dict[str, Any] = {}
    if category is not None:
        where.append("p.category = :cat")
        params["cat"] = category

    sql = text(
        "SELECT COUNT(DISTINCT s.id) AS n FROM shipments s "
        "JOIN orders o      ON o.id = s.order_id "
        "JOIN order_items oi ON oi.order_id = o.id "
        "JOIN products p     ON p.id = oi.product_id "
        "WHERE " + " AND ".join(where)
    )
    n = int(session.execute(sql, params).scalar() or 0)
    if n == 0:
        return 0.0, 0, "No RTO shipments recorded in the data window."
    per_rto = costs.rto_loss()
    basis = (
        f"{n} RTO shipments at Rs {per_rto:,.0f} each (forward + reverse leg Rs "
        f"{costs.rto_logistics_loss:,.0f} plus re-inwarding Rs "
        f"{costs.rto_handling_loss:,.0f}). Observed loss in the data window, "
        f"not a forecast."
    )
    return n * per_rto, n, basis


def build_recommendations(
    session: Session,
    costs: CostModel,
    max_product_recs: int = 12,
) -> list[Recommendation]:
    """Aggregate review aspects into ranked, evidence-backed seller actions."""
    out: list[Recommendation] = []

    # ---- product-level ----
    product_rows = session.execute(text("""
        SELECT ra.product_id, ra.aspect, p.title, p.category,
               COUNT(*) FILTER (WHERE ra.sentiment = 'NEGATIVE') AS neg,
               COUNT(*) AS total
        FROM review_aspects ra
        JOIN products p ON p.id = ra.product_id
        WHERE ra.product_id IS NOT NULL
        GROUP BY ra.product_id, ra.aspect, p.title, p.category
        HAVING COUNT(*) >= :min_reviews
        """), {"min_reviews": MIN_REVIEWS_PRODUCT}).mappings().all()

    for row in product_rows:
        total, neg = int(row["total"]), int(row["neg"])
        share = neg / total if total else 0.0
        if share < MIN_NEGATIVE_SHARE or neg < 3:
            continue
        aspect = row["aspect"]
        problem, recommendation = ASPECT_RECOMMENDATION.get(aspect, ("", ""))
        if not problem:
            continue
        impact, n_events, basis = _observed_return_loss(
            session, aspect, costs, product_id=int(row["product_id"])
        )
        out.append(Recommendation(
            scope="PRODUCT", aspect=aspect, problem=problem,
            recommendation=recommendation,
            priority=_priority(share, neg, impact),
            supporting_review_count=neg, negative_share=share,
            evidence={
                "negative_reviews": neg, "reviews_mentioning_aspect": total,
                "negative_share_pct": round(share * 100, 1),
                "matching_return_events": n_events,
            },
            estimated_business_impact=impact, impact_basis=basis,
            linked_risk_signal=ASPECT_RISK_SIGNAL.get(aspect),
            category=row["category"], product_id=int(row["product_id"]),
            product_title=row["title"],
            affected=f"{row['title']} ({row['category']})",
        ))

    # ---- category-level ----
    category_rows = session.execute(text("""
        SELECT p.category, ra.aspect,
               COUNT(*) FILTER (WHERE ra.sentiment = 'NEGATIVE') AS neg,
               COUNT(*) AS total
        FROM review_aspects ra
        JOIN products p ON p.id = ra.product_id
        GROUP BY p.category, ra.aspect
        HAVING COUNT(*) >= :min_reviews
        """), {"min_reviews": MIN_REVIEWS_CATEGORY}).mappings().all()

    for row in category_rows:
        total, neg = int(row["total"]), int(row["neg"])
        share = neg / total if total else 0.0
        if share < MIN_NEGATIVE_SHARE:
            continue
        aspect = row["aspect"]
        problem, recommendation = ASPECT_RECOMMENDATION.get(aspect, ("", ""))
        if not problem:
            continue
        if aspect in ("DELIVERY", "PACKAGING"):
            impact, n_events, basis = _observed_rto_loss(
                session, costs, category=row["category"]
            )
        else:
            impact, n_events, basis = _observed_return_loss(
                session, aspect, costs, category=row["category"]
            )
        out.append(Recommendation(
            scope="CATEGORY", aspect=aspect, problem=problem,
            recommendation=recommendation,
            priority=_priority(share, neg, impact),
            supporting_review_count=neg, negative_share=share,
            evidence={
                "negative_reviews": neg, "reviews_mentioning_aspect": total,
                "negative_share_pct": round(share * 100, 1),
                "matching_loss_events": n_events,
            },
            estimated_business_impact=impact, impact_basis=basis,
            linked_risk_signal=ASPECT_RISK_SIGNAL.get(aspect),
            category=row["category"], affected=f"All {row['category']} products",
        ))

    priority_rank = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    out.sort(key=lambda r: (
        priority_rank.get(r.priority, 9),
        -r.estimated_business_impact,
        -r.supporting_review_count,
    ))

    products = [r for r in out if r.scope == "PRODUCT"][:max_product_recs]
    categories = [r for r in out if r.scope == "CATEGORY"]
    merged = categories + products
    merged.sort(key=lambda r: (
        priority_rank.get(r.priority, 9), -r.estimated_business_impact
    ))
    return merged
