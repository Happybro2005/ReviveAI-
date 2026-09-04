"""Run the Voice-of-Customer pipeline over every stored review.

    python scripts/analyze_reviews.py [--reset] [--limit N] [--batch 2000]

Writes review_analysis, review_aspects and customer_suggestions rows, refreshes
product_voc_signals (the bridge consumed by the return/RTO models), and rebuilds
seller_recommendations.

Run this AFTER generate_data.py and BEFORE train_models.py: the return model
joins product review signals as-of each order date, so those signals must exist
before training.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import insert, select, text  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.db import get_engine, session_scope  # noqa: E402
from app.models import (  # noqa: E402
    CustomerSuggestion,
    ProductVocSignal,
    Review,
    ReviewAnalysis,
    ReviewAspect,
    SellerRecommendation,
)
from ml.decision.economics import CostModel  # noqa: E402
from ml.nlp.pipeline import analyze_review  # noqa: E402
from ml.nlp.recommendations import build_recommendations  # noqa: E402


def analyze_all(batch_size: int, limit: int | None, reset: bool,
                artifact_dir: Path) -> int:
    engine = get_engine()
    if reset:
        with engine.begin() as conn:
            conn.execute(text(
                "TRUNCATE TABLE review_aspects, customer_suggestions, "
                "review_analysis RESTART IDENTITY CASCADE"
            ))
        print("  cleared previous review analysis")

    with engine.connect() as conn:
        done = {
            r[0] for r in conn.execute(select(ReviewAnalysis.review_id)).fetchall()
        }
        total_reviews = conn.execute(
            text("SELECT COUNT(*) FROM reviews")
        ).scalar_one()

    print(f"  {total_reviews:,} reviews, {len(done):,} already analysed")

    processed = 0
    offset = 0
    t0 = time.time()

    while True:
        with engine.connect() as conn:
            rows = conn.execute(
                select(Review.id, Review.review_text, Review.rating, Review.product_id)
                .order_by(Review.id)
                .offset(offset)
                .limit(batch_size)
            ).all()
        if not rows:
            break
        offset += len(rows)

        analyses: list[dict] = []
        aspects: list[dict] = []
        suggestions: list[dict] = []

        for review_id, review_text, rating, product_id in rows:
            if review_id in done:
                continue
            if not review_text or not review_text.strip():
                continue  # empty reviews carry no signal
            result = analyze_review(review_text, rating=rating,
                                    artifact_dir=artifact_dir)
            analyses.append({
                "review_id": review_id,
                "language": result.language,
                "sentiment": result.sentiment.sentiment,
                "sentiment_score": result.sentiment.sentiment_score,
                "confidence": result.sentiment.confidence,
                "priority": result.priority,
                "business_impact": result.business_impact,
                "topics": json.dumps(result.topics),
                "model_version": result.sentiment.model_version,
            })
            for a in result.aspects:
                aspects.append({
                    "review_id": review_id, "product_id": product_id,
                    "aspect": a.aspect, "sentiment": a.sentiment,
                    "sentiment_score": a.sentiment_score,
                    "evidence_span": a.evidence_span[:2000],
                })
            for s in result.suggestions:
                suggestions.append({
                    "review_id": review_id, "product_id": product_id,
                    "aspect": s.aspect, "suggestion_text": s.suggestion_text[:2000],
                    "normalized_suggestion": s.normalized_suggestion[:120],
                    "source_span": s.source_span[:2000],
                })
            processed += 1
            if limit and processed >= limit:
                break

        with session_scope() as s:
            if analyses:
                s.execute(insert(ReviewAnalysis.__table__), analyses)
            if aspects:
                s.execute(insert(ReviewAspect.__table__), aspects)
            if suggestions:
                s.execute(insert(CustomerSuggestion.__table__), suggestions)

        rate = processed / max(time.time() - t0, 0.001)
        print(f"    analysed {processed:,} reviews ({rate:,.0f}/s)", end="\r")

        if limit and processed >= limit:
            break

    print(f"    analysed {processed:,} reviews in {time.time() - t0:.1f}s      ")
    return processed


def refresh_product_signals() -> int:
    """Recompute per-product review signals consumed by the PROTECT models."""
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE TABLE product_voc_signals RESTART IDENTITY"))
        rows = conn.execute(text("""
            SELECT r.product_id,
                   COUNT(DISTINCT r.id) AS review_count,
                   COUNT(DISTINCT r.id) FILTER (
                       WHERE ra_any.sentiment = 'NEGATIVE') AS negative_reviews,
                   COUNT(DISTINCT r.id) FILTER (
                       WHERE ra_any.aspect = 'SIZE_FIT'        AND ra_any.sentiment = 'NEGATIVE') AS size_fit,
                   COUNT(DISTINCT r.id) FILTER (
                       WHERE ra_any.aspect = 'PRODUCT_QUALITY' AND ra_any.sentiment = 'NEGATIVE') AS quality,
                   COUNT(DISTINCT r.id) FILTER (
                       WHERE ra_any.aspect = 'DELIVERY'        AND ra_any.sentiment = 'NEGATIVE') AS delivery,
                   COUNT(DISTINCT r.id) FILTER (
                       WHERE ra_any.aspect = 'PACKAGING'       AND ra_any.sentiment = 'NEGATIVE') AS packaging,
                   COUNT(DISTINCT r.id) FILTER (
                       WHERE ra_any.aspect = 'CUSTOMER_SUPPORT' AND ra_any.sentiment = 'NEGATIVE') AS support
            FROM reviews r
            LEFT JOIN review_aspects ra_any ON ra_any.review_id = r.id
            WHERE r.product_id IS NOT NULL
            GROUP BY r.product_id
        """)).mappings().all()

        payload = []
        now = datetime.now(timezone.utc)
        for row in rows:
            n = max(int(row["review_count"]), 1)
            payload.append({
                "product_id": row["product_id"], "computed_at": now,
                "review_count": int(row["review_count"]),
                "negative_share": int(row["negative_reviews"]) / n,
                "size_fit_complaint_rate": int(row["size_fit"]) / n,
                "quality_complaint_rate": int(row["quality"]) / n,
                "delivery_complaint_rate": int(row["delivery"]) / n,
                "packaging_complaint_rate": int(row["packaging"]) / n,
                "support_complaint_rate": int(row["support"]) / n,
            })
        if payload:
            conn.execute(insert(ProductVocSignal.__table__), payload)
    print(f"  product_voc_signals refreshed for {len(payload):,} products")
    return len(payload)


def rebuild_recommendations() -> int:
    engine = get_engine()
    costs = CostModel()
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE TABLE seller_recommendations RESTART IDENTITY"))
    with session_scope() as s:
        recs = build_recommendations(s, costs)
        now = datetime.now(timezone.utc)
        for r in recs:
            s.add(SellerRecommendation(
                generated_at=now, scope=r.scope, category=r.category,
                product_id=r.product_id, aspect=r.aspect, problem=r.problem,
                recommendation=r.recommendation, priority=r.priority,
                supporting_review_count=r.supporting_review_count,
                negative_share=r.negative_share,
                evidence=json.dumps(r.evidence),
                estimated_business_impact=r.estimated_business_impact,
                impact_basis=r.impact_basis,
                linked_risk_signal=r.linked_risk_signal,
            ))
    print(f"  seller_recommendations rebuilt: {len(recs)} recommendations")
    return len(recs)


def main() -> int:
    ap = argparse.ArgumentParser(description="Analyse reviews (Voice of Customer)")
    ap.add_argument("--reset", action="store_true",
                    help="delete existing analysis and re-run from scratch")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--batch", type=int, default=2000)
    args = ap.parse_args()

    settings = get_settings()
    print("ReviveAI review analysis")
    print("  DISCLOSURE: reviews are synthetic demo data.")

    analyze_all(args.batch, args.limit, args.reset, settings.artifact_path)
    refresh_product_signals()
    rebuild_recommendations()
    print("\nDone. Next: python scripts/train_models.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
