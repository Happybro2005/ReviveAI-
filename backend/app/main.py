"""ReviveAI FastAPI application."""
from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from ml.common import ModelNotTrained

from .config import SYNTHETIC_DATA_DISCLOSURE, get_settings
from .routers import (
    customer,
    dashboard,
    decision,
    health,
    protection,
    recovery,
    reviews,
    simulator,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-5s [%(name)s] %(message)s",
)
logger = logging.getLogger("reviveai")

settings = get_settings()

app = FastAPI(
    title="ReviveAI",
    version="1.0.0",
    description=(
        "AI revenue intelligence platform: recover lost revenue, protect future "
        "revenue, and turn customer feedback into profitable actions.\n\n"
        f"**{SYNTHETIC_DATA_DISCLOSURE}**"
    ),
    docs_url="/docs",
    openapi_url="/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

for module in (
    health, dashboard, recovery, protection, reviews, customer, decision, simulator
):
    app.include_router(module.router, prefix="/api")


# --------------------------------------------------------------------------
# Error handling: structured, logged, and never leaking internals to the client.
# --------------------------------------------------------------------------
def _serialisable_errors(errors: list[dict]) -> list[dict]:
    """Make Pydantic's error list safe to JSON-encode.

    When a `field_validator` raises a bare ValueError, Pydantic v2 puts the
    exception *object* into ctx["error"]. Handing that to JSONResponse raises
    "Object of type ValueError is not JSON serializable", which turns a 422 into
    a 500 and hides the real validation message from the caller.
    """
    cleaned: list[dict] = []
    for error in errors:
        item = dict(error)
        ctx = item.get("ctx")
        if isinstance(ctx, dict):
            item["ctx"] = {
                k: (str(v) if isinstance(v, BaseException) else v)
                for k, v in ctx.items()
            }
        # `input` can be any object the caller sent; keep it printable.
        if "input" in item:
            value = item["input"]
            if not isinstance(value, (str, int, float, bool, type(None), list, dict)):
                item["input"] = str(value)
        cleaned.append(item)
    return cleaned


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    errors = _serialisable_errors(exc.errors())
    # Surface the first human-readable message rather than a generic sentence.
    first = errors[0].get("msg") if errors else None
    return JSONResponse(
        status_code=422,
        content={
            "error": "validation_error",
            "message": first or "The request body failed validation.",
            "detail": errors,
        },
    )


@app.exception_handler(ModelNotTrained)
async def model_not_trained(request: Request, exc: ModelNotTrained) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={
            "error": "model_not_trained",
            "message": str(exc),
            "detail": "Run: cd backend && python scripts/train_models.py",
        },
    )


@app.exception_handler(SQLAlchemyError)
async def database_error(request: Request, exc: SQLAlchemyError) -> JSONResponse:
    logger.exception("Database error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=503,
        content={
            "error": "database_error",
            "message": "The database is unavailable or the query failed.",
            "detail": "Check DATABASE_URL in .env and that migrations have been applied.",
        },
    )


@app.exception_handler(ValueError)
async def value_error(request: Request, exc: ValueError) -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content={"error": "bad_request", "message": str(exc)},
    )


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={
            "error": "internal_error",
            "message": "An unexpected error occurred. See the server log for details.",
        },
    )


@app.get("/", tags=["system"])
def root() -> dict[str, Any]:
    return {
        "name": "ReviveAI",
        "tagline": "Recover Lost Revenue. Protect Future Revenue. Listen to Customers.",
        "version": app.version,
        "docs": "/docs",
        "health": "/api/health",
        "disclosure": SYNTHETIC_DATA_DISCLOSURE,
    }
