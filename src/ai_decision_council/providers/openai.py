"""Direct OpenAI API provider adapter.

Uses the OpenAI Chat Completions endpoint directly (not via OpenRouter).
Compatible with ``gpt-4o``, ``gpt-4-turbo``, ``o1``, etc.

Configuration
-------------
    provider=openai
    LLM_COUNCIL_API_KEY or OPENAI_API_KEY
    LLM_COUNCIL_API_URL  (optional, default: https://api.openai.com/v1/chat/completions)
"""

from __future__ import annotations

from typing import Dict, List

import httpx

from .base import (
    ProviderAuthError,
    ProviderConfigError,
    ProviderConnectionError,
    ProviderRateLimitError,
    ProviderResponse,
    ProviderResponseError,
    ProviderTimeoutError,
)
from .openrouter import OpenRouterAdapter


class OpenAIAdapter(OpenRouterAdapter):
    """Provider adapter for the direct OpenAI Chat Completions API.

    The wire format is identical to OpenRouter, so we inherit the full
    implementation and only change the default base URL and auth header.
    """

    DEFAULT_API_URL = "https://api.openai.com/v1/chat/completions"

    def __init__(
        self,
        api_key: str | None,
        api_url: str | None = None,
        max_retries: int = 2,
        retry_backoff_seconds: float = 0.5,
    ) -> None:
        super().__init__(
            api_key=api_key,
            api_url=api_url or self.DEFAULT_API_URL,
            max_retries=max_retries,
            retry_backoff_seconds=retry_backoff_seconds,
        )
