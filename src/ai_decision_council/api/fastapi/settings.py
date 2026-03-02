"""API settings and helper env-readers for the FastAPI integration."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_list(name: str, default: list[str]) -> list[str]:
    raw = os.getenv(name)
    if raw is None:
        return default
    items = [part.strip() for part in raw.split(",") if part.strip()]
    return items or default


@dataclass(frozen=True)
class APISettings:
    """Runtime settings for the FastAPI integration."""

    api_prefix: str = "/v1"
    data_dir: str = "data/conversations"
    cors_origins: tuple[str, ...] = ("http://localhost:5173", "http://localhost:3000")
    rate_limit_window_seconds: int = 60
    rate_limit_max_requests: int = 8
    rate_limit_max_concurrent: int = 2
    max_content_chars: int = 20_000
    app_title: str = "LLM Council API"
    app_description: str = (
        "Versioned FastAPI integration for ai-decision-council. "
        "Use as a reusable module or standalone service."
    )

    @classmethod
    def from_env(cls) -> "APISettings":
        return cls(
            api_prefix=os.getenv("LLM_COUNCIL_API_PREFIX", "/v1"),
            data_dir=os.getenv("LLM_COUNCIL_DATA_DIR", "data/conversations"),
            cors_origins=tuple(
                _env_list(
                    "LLM_COUNCIL_CORS_ORIGINS",
                    ["http://localhost:5173", "http://localhost:3000"],
                )
            ),
            rate_limit_window_seconds=max(
                1, _env_int("LLM_COUNCIL_REFERENCE_RATE_LIMIT_WINDOW_SECONDS", 60)
            ),
            rate_limit_max_requests=max(
                1, _env_int("LLM_COUNCIL_REFERENCE_RATE_LIMIT_MAX_REQUESTS", 8)
            ),
            rate_limit_max_concurrent=max(
                1, _env_int("LLM_COUNCIL_REFERENCE_RATE_LIMIT_MAX_CONCURRENT", 2)
            ),
            max_content_chars=max(
                1, _env_int("LLM_COUNCIL_REFERENCE_MAX_CONTENT_CHARS", 20_000)
            ),
        )

