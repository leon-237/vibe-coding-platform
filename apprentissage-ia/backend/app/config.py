"""Runtime configuration, read from environment variables (see .env.example)."""
from __future__ import annotations

import os
from dataclasses import dataclass


def _env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    return value if value not in (None, "") else default


@dataclass(frozen=True)
class Settings:
    database_url: str
    secret_key: str
    token_ttl_hours: int
    # AI provider (Anthropic)
    anthropic_api_key: str | None
    anthropic_base_url: str
    model_simple: str
    model_complex: str
    # Estimated prices in USD per million tokens. Must be set to the official
    # price list of the models in use: the defaults are placeholders.
    ai_input_usd_per_mtok: float
    ai_output_usd_per_mtok: float
    # Used only for the margin estimate in the admin dashboard.
    fcfa_per_usd: float
    # Hard stop on total AI spend per UTC day (all users).
    daily_ai_spend_cap_usd: float
    # Payments (Flutterwave)
    flutterwave_secret_key: str | None
    flutterwave_webhook_hash: str | None
    flutterwave_base_url: str
    public_app_url: str
    max_upload_mb: int


def get_settings() -> Settings:
    return Settings(
        database_url=_env("DATABASE_URL", "sqlite:///./apprentissage.db") or "",
        secret_key=_env("SECRET_KEY", "dev-only-change-me") or "",
        token_ttl_hours=int(_env("TOKEN_TTL_HOURS", "720") or 720),
        anthropic_api_key=_env("ANTHROPIC_API_KEY"),
        anthropic_base_url=_env("ANTHROPIC_BASE_URL", "https://api.anthropic.com") or "",
        model_simple=_env("AI_MODEL_SIMPLE", "claude-haiku-5-5") or "",
        model_complex=_env("AI_MODEL_COMPLEX", "claude-sonnet-5-5") or "",
        ai_input_usd_per_mtok=float(_env("AI_INPUT_USD_PER_MTOK", "1.0") or 0),
        ai_output_usd_per_mtok=float(_env("AI_OUTPUT_USD_PER_MTOK", "5.0") or 0),
        fcfa_per_usd=float(_env("FCFA_PER_USD", "600") or 600),
        daily_ai_spend_cap_usd=float(_env("DAILY_AI_SPEND_CAP_USD", "50") or 50),
        flutterwave_secret_key=_env("FLW_SECRET_KEY"),
        flutterwave_webhook_hash=_env("FLW_WEBHOOK_HASH"),
        flutterwave_base_url=_env("FLW_BASE_URL", "https://api.flutterwave.com/v3") or "",
        public_app_url=_env("PUBLIC_APP_URL", "http://localhost:8000") or "",
        max_upload_mb=int(_env("MAX_UPLOAD_MB", "15") or 15),
    )
