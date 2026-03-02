"""Ollama local-server provider adapter.

Ollama exposes an OpenAI-compatible ``/v1/chat/completions`` endpoint, so
this adapter reuses the OpenRouter implementation with a local base URL and
no authentication requirement.

Configuration
-------------
    provider=ollama
    LLM_COUNCIL_API_URL  (default: http://localhost:11434/v1/chat/completions)
    No API key required.

    Models use the bare Ollama model name, e.g.:
        LLM_COUNCIL_MODELS=llama3.2,mistral,qwen2.5
"""

from __future__ import annotations

from .openrouter import OpenRouterAdapter


class OllamaAdapter(OpenRouterAdapter):
    """Provider adapter for a local Ollama server.

    Ollama's OpenAI-compatible endpoint requires no auth token.
    Models are referenced by their Ollama pull name (e.g. ``llama3.2``).
    """

    DEFAULT_API_URL = "http://localhost:11434/v1/chat/completions"

    def __init__(
        self,
        api_key: str | None = None,
        api_url: str | None = None,
        max_retries: int = 2,
        retry_backoff_seconds: float = 0.5,
    ) -> None:
        # Ollama doesn't need a key; override config error guard by using a
        # dummy sentinel when no key is provided so the parent validation
        # doesn't raise ProviderConfigError.
        super().__init__(
            api_key=api_key or "ollama",  # sentinel – Ollama ignores the header
            api_url=api_url or self.DEFAULT_API_URL,
            max_retries=max_retries,
            retry_backoff_seconds=retry_backoff_seconds,
        )
