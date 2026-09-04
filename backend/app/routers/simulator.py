"""Revenue simulator endpoint."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from ml.decision.simulator import SimulatorInputError, SimulatorInputs, simulate

from ..config import SYNTHETIC_DATA_DISCLOSURE
from ..db import get_db
from ..deps import get_costs

router = APIRouter(prefix="/simulator", tags=["simulator"])


class SimulatorRequest(BaseModel):
    checkout_volume: int = Field(ge=0, le=100_000_000)
    average_order_value: float = Field(ge=0, le=10_000_000)
    abandonment_rate: float = Field(ge=0, le=1)
    recovery_rate: float = Field(ge=0, le=1)
    discount_rate: float = Field(default=0.0, ge=0, le=1)
    gross_margin: float = Field(default=0.35, ge=0, le=1)
    delivery_cost_per_order: float = Field(default=0.0, ge=0, le=1_000_000)
    intervention_cost_per_contact: float = Field(default=0.0, ge=0, le=1_000_000)
    contact_coverage: float = Field(default=1.0, ge=0, le=1)


@router.post("/calculate")
def calculate(body: SimulatorRequest):
    try:
        result = simulate(SimulatorInputs(**body.model_dump()))
    except SimulatorInputError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    result["disclosure"] = SYNTHETIC_DATA_DISCLOSURE
    result["formula_reference"] = "/docs/business-metrics.md"
    return result


@router.get("/defaults")
def defaults(db: Session = Depends(get_db)):
    """Seed the simulator from the actual dataset so it opens on real numbers."""
    costs = get_costs()
    row = db.execute(text("""
        SELECT
          (SELECT COUNT(*) FROM checkout_sessions
             WHERE started_at >= NOW() - INTERVAL '30 days') AS volume,
          (SELECT COALESCE(AVG(order_value), 0) FROM orders
             WHERE order_date >= NOW() - INTERVAL '180 days') AS aov,
          (SELECT COUNT(*) FROM checkout_sessions
             WHERE started_at >= NOW() - INTERVAL '180 days') AS sessions,
          (SELECT COUNT(*) FROM checkout_sessions
             WHERE abandoned AND started_at >= NOW() - INTERVAL '180 days') AS abandoned,
          (SELECT COUNT(*) FROM abandoned_carts
             WHERE abandoned_at >= NOW() - INTERVAL '180 days') AS carts,
          (SELECT COUNT(*) FROM abandoned_carts
             WHERE recovered AND abandoned_at >= NOW() - INTERVAL '180 days') AS recovered
    """)).mappings().one()

    sessions = int(row["sessions"]) or 0
    carts = int(row["carts"]) or 0
    return {
        "checkout_volume": int(row["volume"]) or 10000,
        "average_order_value": round(float(row["aov"]), 2),
        "abandonment_rate": round(int(row["abandoned"]) / sessions, 4) if sessions else 0.3,
        "recovery_rate": round(int(row["recovered"]) / carts, 4) if carts else 0.2,
        "discount_rate": 0.05,
        "gross_margin": costs.gross_margin,
        "delivery_cost_per_order": 60.0,
        "intervention_cost_per_contact": costs.email,
        "contact_coverage": 1.0,
        "source": (
            "Defaults are the observed rates in the last 180 days of the synthetic "
            "dataset; the 30-day checkout volume is used as the monthly volume."
        ),
        "disclosure": SYNTHETIC_DATA_DISCLOSURE,
    }
