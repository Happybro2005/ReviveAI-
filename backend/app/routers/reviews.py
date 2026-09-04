"""LISTEN pillar endpoints: review analysis, insights, recommendations."""
from __future__ import annotations

import csv
import io
import json
from collections import Counter
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import text
from sqlalchemy.orm import Session

from ml.decision.economics import CostModel
from ml.nlp.lexicon import ASPECT_LABELS, ASPECT_RISK_SIGNAL
from ml.nlp.pipeline import analyze_review
from ml.nlp.recommendations import build_recommendations

from ..config import SYNTHETIC_DATA_DISCLOSURE, get_settings
from ..db import get_db
from ..schemas import ReviewAnalyzeRequest

router = APIRouter(prefix="/reviews", tags=["voice-of-customer"])

MAX_CSV_BYTES = 12 * 1024 * 1024      # 12 MB
MAX_CSV_ROWS = 20_000
REQUIRED_CSV_COLUMNS = {"review_text"}
OPTIONAL_CSV_COLUMNS = {"review_id", "customer_id", "product_id", "rating", "review_date"}


def _persist(db: Session, text_body: str, rating: int | None,
             product_id: int | None, customer_id: int | None,
             result, source: str) -> int:
    """Insert a review and its analysis. Returns the new review id."""
    now = datetime.now(timezone.utc)
    review_id = db.execute(text("""
        INSERT INTO reviews (review_ref, customer_id, product_id, order_id, rating,
                             review_text, review_date, source, created_at, updated_at)
        VALUES (:ref, :cust, :prod, NULL, :rating, :body, :now, :source, :now, :now)
        RETURNING id
    """), {
        "ref": f"API{int(now.timestamp() * 1000)}{abs(hash(text_body)) % 100000}",
        "cust": customer_id, "prod": product_id,
        "rating": rating if rating is not None else 3,
        "body": text_body, "now": now, "source": source,
    }).scalar_one()

    db.execute(text("""
        INSERT INTO review_analysis (review_id, language, sentiment, sentiment_score,
                                     confidence, priority, business_impact, topics,
                                     model_version, created_at, updated_at)
        VALUES (:rid, :lang, :sent, :score, :conf, :prio, :impact, :topics, :ver,
                :now, :now)
    """), {
        "rid": review_id, "lang": result.language,
        "sent": result.sentiment.sentiment,
        "score": result.sentiment.sentiment_score,
        "conf": result.sentiment.confidence, "prio": result.priority,
        "impact": result.business_impact, "topics": json.dumps(result.topics),
        "ver": result.sentiment.model_version, "now": now,
    })
    for a in result.aspects:
        db.execute(text("""
            INSERT INTO review_aspects (review_id, product_id, aspect, sentiment,
                                        sentiment_score, evidence_span,
                                        created_at, updated_at)
            VALUES (:rid, :pid, :aspect, :sent, :score, :span, :now, :now)
            ON CONFLICT (review_id, aspect) DO NOTHING
        """), {
            "rid": review_id, "pid": product_id, "aspect": a.aspect,
            "sent": a.sentiment, "score": a.sentiment_score,
            "span": a.evidence_span[:2000], "now": now,
        })
    for s in result.suggestions:
        db.execute(text("""
            INSERT INTO customer_suggestions (review_id, product_id, aspect,
                                              suggestion_text, normalized_suggestion,
                                              source_span, created_at, updated_at)
            VALUES (:rid, :pid, :aspect, :txt, :norm, :span, :now, :now)
        """), {
            "rid": review_id, "pid": product_id, "aspect": s.aspect,
            "txt": s.suggestion_text[:2000],
            "norm": s.normalized_suggestion[:120],
            "span": s.source_span[:2000], "now": now,
        })
    return int(review_id)


@router.post("/analyze")
def analyze(body: ReviewAnalyzeRequest, db: Session = Depends(get_db)):
    """Analyse a single review. Optionally persist it."""
    settings = get_settings()
    result = analyze_review(
        body.review_text, rating=body.rating, artifact_dir=settings.artifact_path
    )
    payload = result.to_dict()
    payload["review_id"] = None

    if body.persist:
        if body.product_id is not None:
            exists = db.execute(
                text("SELECT 1 FROM products WHERE id = :id"), {"id": body.product_id}
            ).scalar()
            if not exists:
                raise HTTPException(
                    status_code=404, detail=f"Product {body.product_id} not found"
                )
        payload["review_id"] = _persist(
            db, result.text, body.rating, body.product_id, body.customer_id,
            result, "API",
        )
        db.commit()

    payload["disclosure"] = SYNTHETIC_DATA_DISCLOSURE
    return payload


@router.post("/bulk-analyze")
async def bulk_analyze(
    file: UploadFile = File(...),
    persist: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    """Analyse a CSV of reviews.

    Expected columns: review_text (required); review_id, customer_id, product_id,
    rating, review_date (optional). Malformed rows are skipped and reported
    rather than failing the whole upload.
    """
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    if len(raw) > MAX_CSV_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds {MAX_CSV_BYTES // (1024 * 1024)} MB limit.",
        )

    # Tolerate the encodings spreadsheets actually produce.
    decoded: str | None = None
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            decoded = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if decoded is None:
        raise HTTPException(
            status_code=400,
            detail="Could not decode the file. Save it as UTF-8 CSV and retry.",
        )

    try:
        dialect = csv.Sniffer().sniff(decoded[:4096], delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(decoded), dialect=dialect)

    if not reader.fieldnames:
        raise HTTPException(status_code=400, detail="CSV has no header row.")
    headers = {(h or "").strip().lower() for h in reader.fieldnames}
    missing = REQUIRED_CSV_COLUMNS - headers
    if missing:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Missing required column(s): {', '.join(sorted(missing))}. "
                f"Expected review_text plus optional "
                f"{', '.join(sorted(OPTIONAL_CSV_COLUMNS))}."
            ),
        )

    settings = get_settings()
    errors: list[str] = []
    seen_texts: set[str] = set()
    rows_received = rows_processed = rows_skipped = duplicates = persisted = 0

    sentiment_counts: Counter[str] = Counter()
    aspect_counts: dict[str, Counter[str]] = {}
    suggestion_counts: Counter[str] = Counter()
    suggestion_aspect: dict[str, str] = {}
    ratings: list[int] = []

    for raw_row in reader:
        rows_received += 1
        if rows_received > MAX_CSV_ROWS:
            errors.append(
                f"Stopped at {MAX_CSV_ROWS:,} rows; the rest of the file was ignored."
            )
            break

        row = {(k or "").strip().lower(): (v or "") for k, v in raw_row.items()}
        body_text = (row.get("review_text") or "").strip()
        if not body_text:
            rows_skipped += 1
            continue
        if len(body_text) > 8000:
            body_text = body_text[:8000]
            errors.append(f"Row {rows_received}: review truncated to 8000 characters.")

        key = body_text.lower()
        if key in seen_texts:
            duplicates += 1
            continue
        seen_texts.add(key)

        rating: int | None = None
        if row.get("rating"):
            try:
                parsed = int(float(row["rating"]))
                rating = parsed if 1 <= parsed <= 5 else None
                if rating is None:
                    errors.append(f"Row {rows_received}: rating out of range, ignored.")
            except ValueError:
                errors.append(f"Row {rows_received}: rating not numeric, ignored.")

        product_id: int | None = None
        if row.get("product_id"):
            try:
                product_id = int(float(row["product_id"]))
            except ValueError:
                errors.append(f"Row {rows_received}: product_id not numeric, ignored.")

        customer_id: int | None = None
        if row.get("customer_id"):
            try:
                customer_id = int(float(row["customer_id"]))
            except ValueError:
                pass

        try:
            result = analyze_review(
                body_text, rating=rating, artifact_dir=settings.artifact_path
            )
        except Exception as exc:
            rows_skipped += 1
            errors.append(f"Row {rows_received}: analysis failed ({type(exc).__name__}).")
            continue

        rows_processed += 1
        sentiment_counts[result.sentiment.sentiment] += 1
        if rating is not None:
            ratings.append(rating)
        for a in result.aspects:
            aspect_counts.setdefault(a.aspect, Counter())[a.sentiment] += 1
        for s in result.suggestions:
            suggestion_counts[s.normalized_suggestion] += 1
            suggestion_aspect[s.normalized_suggestion] = s.aspect

        if persist:
            valid_product = product_id
            if product_id is not None:
                ok = db.execute(
                    text("SELECT 1 FROM products WHERE id = :id"), {"id": product_id}
                ).scalar()
                if not ok:
                    valid_product = None
            try:
                _persist(db, result.text, rating, valid_product, customer_id,
                         result, "CSV_UPLOAD")
                persisted += 1
            except Exception as exc:
                errors.append(f"Row {rows_received}: could not save ({type(exc).__name__}).")

    if persist and persisted:
        db.commit()

    aspect_analysis = []
    for aspect, counts in aspect_counts.items():
        total = sum(counts.values())
        aspect_analysis.append({
            "aspect": aspect,
            "aspect_label": ASPECT_LABELS.get(aspect, aspect),
            "total": total,
            "positive": counts.get("POSITIVE", 0),
            "negative": counts.get("NEGATIVE", 0),
            "neutral": counts.get("NEUTRAL", 0),
            "positive_share": round(counts.get("POSITIVE", 0) / total, 4) if total else 0.0,
            "negative_share": round(counts.get("NEGATIVE", 0) / total, 4) if total else 0.0,
            "risk_signal": ASPECT_RISK_SIGNAL.get(aspect),
        })
    aspect_analysis.sort(key=lambda a: -a["negative"])

    top_issues = [
        {
            "aspect": a["aspect"], "aspect_label": a["aspect_label"],
            "negative_mentions": a["negative"],
            "share_of_reviews": round(a["negative"] / rows_processed, 4)
            if rows_processed else 0.0,
            "risk_signal": a["risk_signal"],
        }
        for a in aspect_analysis if a["negative"] > 0
    ][:10]

    recommendations: list[dict[str, Any]] = []
    if persist and persisted:
        try:
            recommendations = [
                r.to_dict() for r in build_recommendations(db, CostModel())
            ][:10]
        except Exception as exc:
            errors.append(f"Recommendation rebuild failed: {type(exc).__name__}.")

    return {
        "rows_received": rows_received,
        "rows_processed": rows_processed,
        "rows_skipped": rows_skipped,
        "duplicates_skipped": duplicates,
        "persisted": persisted,
        "errors": errors[:50],
        "sentiment_distribution": dict(sentiment_counts),
        "average_rating": round(sum(ratings) / len(ratings), 3) if ratings else None,
        "top_issues": top_issues,
        "top_suggestions": [
            {
                "suggestion": s, "count": c,
                "aspect": suggestion_aspect.get(s),
                "aspect_label": ASPECT_LABELS.get(suggestion_aspect.get(s, ""), ""),
            }
            for s, c in suggestion_counts.most_common(10)
        ],
        "aspect_analysis": aspect_analysis,
        "seller_recommendations": recommendations,
        "disclosure": SYNTHETIC_DATA_DISCLOSURE,
    }


@router.get("/insights")
def insights(db: Session = Depends(get_db), product_id: int | None = None,
             category: str | None = None):
    """Aggregated Voice-of-Customer metrics, computed in the database."""
    where, params = [], {}
    if product_id is not None:
        where.append("r.product_id = :pid")
        params["pid"] = product_id
    if category:
        where.append("p.category = :cat")
        params["cat"] = category
    clause = (" WHERE " + " AND ".join(where)) if where else ""

    totals = db.execute(text(f"""
        SELECT COUNT(*) AS total, COALESCE(AVG(r.rating), 0) AS avg_rating
        FROM reviews r LEFT JOIN products p ON p.id = r.product_id{clause}
    """), params).mappings().one()

    sentiment = db.execute(text(f"""
        SELECT ra.sentiment, COUNT(*) AS count
        FROM review_analysis ra
        JOIN reviews r ON r.id = ra.review_id
        LEFT JOIN products p ON p.id = r.product_id{clause}
        GROUP BY ra.sentiment
    """), params).mappings().all()

    aspects = db.execute(text(f"""
        SELECT a.aspect,
               COUNT(*) AS total,
               COUNT(*) FILTER (WHERE a.sentiment = 'POSITIVE') AS positive,
               COUNT(*) FILTER (WHERE a.sentiment = 'NEGATIVE') AS negative,
               COUNT(*) FILTER (WHERE a.sentiment = 'NEUTRAL')  AS neutral
        FROM review_aspects a
        JOIN reviews r ON r.id = a.review_id
        LEFT JOIN products p ON p.id = r.product_id{clause}
        GROUP BY a.aspect ORDER BY negative DESC
    """), params).mappings().all()

    suggestions = db.execute(text(f"""
        SELECT s.normalized_suggestion, s.aspect, COUNT(*) AS count
        FROM customer_suggestions s
        JOIN reviews r ON r.id = s.review_id
        LEFT JOIN products p ON p.id = r.product_id{clause}
        GROUP BY s.normalized_suggestion, s.aspect
        ORDER BY count DESC LIMIT 12
    """), params).mappings().all()

    analysed = sum(int(s["count"]) for s in sentiment)
    total_reviews = int(totals["total"])

    return {
        "total_reviews": total_reviews,
        "analysed_reviews": analysed,
        "average_rating": round(float(totals["avg_rating"]), 3) if total_reviews else None,
        "sentiment_distribution": {s["sentiment"]: int(s["count"]) for s in sentiment},
        "aspect_analysis": [
            {
                "aspect": a["aspect"],
                "aspect_label": ASPECT_LABELS.get(a["aspect"], a["aspect"]),
                "total": int(a["total"]), "positive": int(a["positive"]),
                "negative": int(a["negative"]), "neutral": int(a["neutral"]),
                "positive_share": round(int(a["positive"]) / int(a["total"]), 4)
                if a["total"] else 0.0,
                "negative_share": round(int(a["negative"]) / int(a["total"]), 4)
                if a["total"] else 0.0,
                "risk_signal": ASPECT_RISK_SIGNAL.get(a["aspect"]),
            }
            for a in aspects
        ],
        "top_concerns": [
            {
                "aspect": a["aspect"],
                "aspect_label": ASPECT_LABELS.get(a["aspect"], a["aspect"]),
                "negative_mentions": int(a["negative"]),
                "share_of_reviews": round(int(a["negative"]) / analysed, 4)
                if analysed else 0.0,
                "risk_signal": ASPECT_RISK_SIGNAL.get(a["aspect"]),
            }
            for a in aspects if int(a["negative"]) > 0
        ][:10],
        "top_suggestions": [
            {
                "suggestion": s["normalized_suggestion"], "aspect": s["aspect"],
                "aspect_label": ASPECT_LABELS.get(s["aspect"], s["aspect"]),
                "count": int(s["count"]),
            }
            for s in suggestions
        ],
        "disclosure": SYNTHETIC_DATA_DISCLOSURE,
    }


@router.get("/recommendations")
def recommendations(
    db: Session = Depends(get_db),
    rebuild: bool = Query(default=False, description="Recompute instead of reading stored rows."),
    limit: int = Query(default=20, ge=1, le=100),
):
    """Evidence-backed seller recommendations derived from review aggregates."""
    if rebuild:
        recs = [r.to_dict() for r in build_recommendations(db, CostModel())][:limit]
        return {"items": recs, "source": "recomputed",
                "disclosure": SYNTHETIC_DATA_DISCLOSURE}

    rows = db.execute(text("""
        SELECT sr.*, p.title AS product_title
        FROM seller_recommendations sr
        LEFT JOIN products p ON p.id = sr.product_id
        ORDER BY CASE sr.priority WHEN 'CRITICAL' THEN 0 WHEN 'HIGH' THEN 1
                                  WHEN 'MEDIUM' THEN 2 ELSE 3 END,
                 sr.estimated_business_impact DESC
        LIMIT :limit
    """), {"limit": limit}).mappings().all()

    return {
        "items": [
            {
                "id": int(r["id"]), "scope": r["scope"], "aspect": r["aspect"],
                "aspect_label": ASPECT_LABELS.get(r["aspect"], r["aspect"]),
                "problem": r["problem"], "recommendation": r["recommendation"],
                "priority": r["priority"],
                "supporting_review_count": int(r["supporting_review_count"]),
                "negative_share": float(r["negative_share"]),
                "evidence": json.loads(r["evidence"]) if r["evidence"] else {},
                "estimated_business_impact": float(r["estimated_business_impact"]),
                "impact_basis": r["impact_basis"],
                "linked_risk_signal": r["linked_risk_signal"],
                "category": r["category"], "product_id": r["product_id"],
                "product_title": r["product_title"],
                "affected": r["product_title"] or (
                    f"All {r['category']} products" if r["category"] else "All products"
                ),
            }
            for r in rows
        ],
        "source": "stored",
        "disclosure": SYNTHETIC_DATA_DISCLOSURE,
    }
