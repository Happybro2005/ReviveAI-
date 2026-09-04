"""Unified decision endpoint spanning both pillars."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ml.common import ModelNotTrained
from ml.decision.decision_engine import decide_protection, decide_recovery
from ml.decision.economics import (
    ASSUMPTION_DISCLOSURE,
    PROTECTION_ACTIONS,
    PROTECTION_EFFECTS,
    RECOVERY_ACTIONS,
    RECOVERY_ACTION_LABELS,
    PROTECTION_ACTION_LABELS,
)

from ..config import SYNTHETIC_DATA_DISCLOSURE
from ..deps import get_costs, get_store
from ..schemas import CheckoutSessionInput
from ..schemas.protection import ProtectionDecisionInput

router = APIRouter(prefix="/decision", tags=["decision"])


class NextBestActionRequest(BaseModel):
    pillar: Literal["RECOVERY", "PROTECTION"]
    session: CheckoutSessionInput | None = None
    order: ProtectionDecisionInput | None = None
    candidate_actions: list[str] | None = Field(
        default=None, description="Restrict the comparison to these actions."
    )


@router.post("/next-best-action")
def next_best_action(body: NextBestActionRequest):
    """Compare candidate actions and return the highest expected-profit choice."""
    store, costs = get_store(), get_costs()

    if body.pillar == "RECOVERY":
        if body.session is None:
            raise HTTPException(
                status_code=422, detail="`session` is required when pillar is RECOVERY."
            )
        if body.candidate_actions:
            unknown = set(body.candidate_actions) - set(RECOVERY_ACTIONS)
            if unknown:
                raise HTTPException(
                    status_code=422,
                    detail=f"Unknown recovery action(s): {', '.join(sorted(unknown))}",
                )
        payload = body.session.model_dump()
        payload["shipping_cart_ratio"] = body.session.shipping_cart_ratio
        try:
            result = decide_recovery(payload, store, costs, body.candidate_actions)
        except ModelNotTrained as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        return result.to_dict()

    if body.order is None:
        raise HTTPException(
            status_code=422, detail="`order` is required when pillar is PROTECTION."
        )
    if body.candidate_actions:
        unknown = set(body.candidate_actions) - set(PROTECTION_ACTIONS)
        if unknown:
            raise HTTPException(
                status_code=422,
                detail=f"Unknown protection action(s): {', '.join(sorted(unknown))}",
            )
    result = decide_protection(
        order={"order_value": body.order.order_value, "is_cod": body.order.is_cod},
        rto_probability=body.order.rto_probability,
        return_probability=body.order.return_probability,
        costs=costs,
        voc_signals=body.order.voc_signals,
        actions=body.candidate_actions,
    )
    return result.to_dict()


@router.get("/actions")
def actions():
    """The action catalogue, with costs and the basis for each effect."""
    costs = get_costs()
    return {
        "recovery": [
            {
                "action": a, "label": RECOVERY_ACTION_LABELS[a],
                "effect_basis": "LEARNED",
                "note": "Uplift estimated by the trained recovery model.",
            }
            for a in RECOVERY_ACTIONS
        ],
        "protection": [
            {
                "action": a, "label": PROTECTION_ACTION_LABELS[a],
                "channel": PROTECTION_EFFECTS[a].channel,
                "rto_reduction": PROTECTION_EFFECTS[a].rto_reduction,
                "return_reduction": PROTECTION_EFFECTS[a].return_reduction,
                "fixed_cost": PROTECTION_EFFECTS[a].fixed_cost,
                "effect_basis": "ASSUMED",
                "note": PROTECTION_EFFECTS[a].basis,
            }
            for a in PROTECTION_ACTIONS
        ],
        "cost_model": costs.to_dict(),
        "assumption_disclosure": ASSUMPTION_DISCLOSURE,
        "disclosure": SYNTHETIC_DATA_DISCLOSURE,
    }
