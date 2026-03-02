"""Reusable ai-decision-council core library."""

from .client import Council
from .config import CouncilConfig
from .schemas import CouncilResult, ModelRunError
from .council import (
    calculate_aggregate_rankings,
    generate_conversation_title,
    parse_ranking_from_text,
    run_full_council,
    stage1_collect_responses,
    stage2_collect_rankings,
    stage3_synthesize_final,
)
from .providers import (
    OpenRouterAdapter,
    ProviderAdapter,
    ProviderAuthError,
    ProviderConfigError,
    ProviderConnectionError,
    ProviderError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderTimeoutError,
)


def create_fastapi_app(*args, **kwargs):
    """Lazy FastAPI app factory import to avoid hard dependency on FastAPI."""
    from .api.fastapi import create_app

    return create_app(*args, **kwargs)


def create_fastapi_router(*args, **kwargs):
    """Lazy FastAPI router factory for embedding in existing apps."""
    from .api.fastapi import create_router

    return create_router(*args, **kwargs)


__all__ = [
    "Council",
    "CouncilConfig",
    "CouncilResult",
    "ModelRunError",
    "ProviderAdapter",
    "OpenRouterAdapter",
    "ProviderError",
    "ProviderConfigError",
    "ProviderAuthError",
    "ProviderRateLimitError",
    "ProviderTimeoutError",
    "ProviderConnectionError",
    "ProviderResponseError",
    "calculate_aggregate_rankings",
    "generate_conversation_title",
    "parse_ranking_from_text",
    "run_full_council",
    "stage1_collect_responses",
    "stage2_collect_rankings",
    "stage3_synthesize_final",
    "create_fastapi_app",
    "create_fastapi_router",
]
