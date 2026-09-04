"""Centralised configuration. All values come from the environment (.env)."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Repository root = two levels above this file (backend/app/config.py -> repo root)
REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    """Runtime settings. Nothing here may be hard-coded to a real credential."""

    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = Field(default="", alias="DATABASE_URL")
    admin_database_url: str = Field(default="", alias="ADMIN_DATABASE_URL")

    api_host: str = Field(default="127.0.0.1", alias="API_HOST")
    api_port: int = Field(default=8000, alias="API_PORT")
    cors_origins: str = Field(
        default="http://localhost:5173,http://127.0.0.1:5173", alias="CORS_ORIGINS"
    )

    artifact_dir: str = Field(default="artifacts", alias="ARTIFACT_DIR")

    seed: int = Field(default=42, alias="SEED")
    n_customers: int = Field(default=8000, alias="N_CUSTOMERS")
    n_products: int = Field(default=600, alias="N_PRODUCTS")
    n_checkout_sessions: int = Field(default=100_000, alias="N_CHECKOUT_SESSIONS")
    n_reviews: int = Field(default=50_000, alias="N_REVIEWS")

    gross_margin: float = Field(default=0.35, alias="GROSS_MARGIN")
    email_cost: float = Field(default=0.5, alias="EMAIL_COST")
    sms_cost: float = Field(default=0.25, alias="SMS_COST")
    whatsapp_cost: float = Field(default=0.35, alias="WHATSAPP_COST")
    call_cost: float = Field(default=18.0, alias="CALL_COST")
    manual_review_cost: float = Field(default=45.0, alias="MANUAL_REVIEW_COST")

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def artifact_path(self) -> Path:
        p = Path(self.artifact_dir)
        if not p.is_absolute():
            p = BACKEND_ROOT / p
        p.mkdir(parents=True, exist_ok=True)
        return p


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


# Disclosure text shown wherever synthetic figures are surfaced.
SYNTHETIC_DATA_DISCLOSURE = (
    "Demo data is synthetic and is used to demonstrate the ReviveAI platform. "
    "Model performance and financial impact figures are simulated/estimated and "
    "should not be interpreted as production results."
)
