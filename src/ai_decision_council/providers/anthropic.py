"""Anthropic Claude API provider adapter.

Communicates directly with the Anthropic Messages API (``/v1/messages``).
The request and response shapes differ from the OpenAI-compatible format, so
this adapter provides its own full ``chat`` implementation.

Configuration
-------------
    provider=anthropic
    LLM_COUNCIL_API_KEY or ANTHROPIC_API_KEY
    LLM_COUNCIL_API_URL  (optional, default: https://api.anthropic.com/v1/messages)

    Recommended models:
        claude-opus-4-5, claude-sonnet-4-5, claude-haiku-3-5
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List

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


_ANTHROPIC_VERSION = "2023-06-01"
_DEFAULT_MAX_TOKENS = 4096


class AnthropicAdapter:
    """Provider adapter for the Anthropic Messages API."""

    DEFAULT_API_URL = "https://api.anthropic.com/v1/messages"

    def __init__(
        self,
        api_key: str | None,
        api_url: str | None = None,
        max_retries: int = 2,
        retry_backoff_seconds: float = 0.5,
        max_tokens: int = _DEFAULT_MAX_TOKENS,
    ) -> None:
        self.api_key = api_key
        self.api_url = api_url or self.DEFAULT_API_URL
        self.max_retries = max_retries
        self.retry_backoff_seconds = retry_backoff_seconds
        self.max_tokens = max_tokens

    async def chat(
        self,
        model: str,
        messages: List[Dict[str, str]],
        timeout: float,
    ) -> ProviderResponse:
        if not self.api_key:
            raise ProviderConfigError("Missing Anthropic API key (ANTHROPIC_API_KEY)")
        if not self.api_url:
            raise ProviderConfigError("Missing Anthropic API URL")

        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": _ANTHROPIC_VERSION,
            "content-type": "application/json",
        }

        # Anthropic requires system messages to be passed separately
        system_content: str | None = None
        user_messages: List[Dict[str, str]] = []
        for msg in messages:
            if msg.get("role") == "system":
                system_content = msg.get("content", "")
            else:
                user_messages.append(msg)

        payload: Dict[str, Any] = {
            "model": model,
            "messages": user_messages,
            "max_tokens": self.max_tokens,
        }
        if system_content is not None:
            payload["system"] = system_content

        attempts = self.max_retries + 1
        for attempt in range(attempts):
            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    response = await client.post(
                        self.api_url,
                        headers=headers,
                        json=payload,
                    )

                if response.status_code in (401, 403):
                    raise ProviderAuthError(
                        f"Anthropic authentication failed for model {model}"
                    )
                if response.status_code == 429:
                    if attempt < self.max_retries:
                        await asyncio.sleep(self.retry_backoff_seconds * (2**attempt))
                        continue
                    raise ProviderRateLimitError(
                        f"Anthropic rate limited for model {model}"
                    )
                if response.status_code >= 500:
                    if attempt < self.max_retries:
                        await asyncio.sleep(self.retry_backoff_seconds * (2**attempt))
                        continue
                    raise ProviderResponseError(
                        f"Anthropic server error for model {model}: HTTP {response.status_code}"
                    )

                response.raise_for_status()
                data = response.json()

                # Anthropic response: {"content": [{"type": "text", "text": "..."}], ...}
                content_blocks = data.get("content", [])
                if not content_blocks:
                    raise ProviderResponseError(
                        f"Empty content from Anthropic model {model}"
                    )

                text_parts = [
                    block.get("text", "")
                    for block in content_blocks
                    if isinstance(block, dict) and block.get("type") == "text"
                ]
                content = "".join(text_parts)

                return ProviderResponse(
                    content=content,
                    reasoning_details=None,
                    raw=data,
                )

            except ProviderAuthError:
                raise
            except ProviderRateLimitError:
                raise
            except ProviderResponseError:
                raise
            except httpx.TimeoutException as exc:
                if attempt < self.max_retries:
                    await asyncio.sleep(self.retry_backoff_seconds * (2**attempt))
                    continue
                raise ProviderTimeoutError(
                    f"Timeout querying Anthropic model {model}"
                ) from exc
            except httpx.TransportError as exc:
                if attempt < self.max_retries:
                    await asyncio.sleep(self.retry_backoff_seconds * (2**attempt))
                    continue
                raise ProviderConnectionError(
                    f"Connection error querying Anthropic model {model}"
                ) from exc
            except Exception as exc:
                raise ProviderResponseError(
                    f"Unhandled Anthropic error for model {model}: {exc}"
                ) from exc

        raise ProviderResponseError(
            f"Exhausted retries for Anthropic model {model}"
        )
