"""OpenRouter provider adapter implementation."""

from __future__ import annotations

import asyncio
from typing import Dict, List

import httpx

from .base import (
    ProviderAdapter,
    ProviderAuthError,
    ProviderConfigError,
    ProviderConnectionError,
    ProviderRateLimitError,
    ProviderResponse,
    ProviderResponseError,
    ProviderTimeoutError,
)


class OpenRouterAdapter(ProviderAdapter):
    """Provider adapter for OpenRouter chat-completions API."""

    def __init__(
        self,
        api_key: str | None,
        api_url: str,
        max_retries: int = 2,
        retry_backoff_seconds: float = 0.5,
    ):
        self.api_key = api_key
        self.api_url = api_url
        self.max_retries = max_retries
        self.retry_backoff_seconds = retry_backoff_seconds

    async def chat(
        self,
        model: str,
        messages: List[Dict[str, str]],
        timeout: float,
    ) -> ProviderResponse:
        if not self.api_key:
            raise ProviderConfigError("Missing provider API key")
        if not self.api_url:
            raise ProviderConfigError("Missing provider API URL")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "messages": messages,
        }

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
                    raise ProviderAuthError(f"Authentication failed for model {model}")
                if response.status_code == 429:
                    if attempt < self.max_retries:
                        await asyncio.sleep(self.retry_backoff_seconds * (2 ** attempt))
                        continue
                    raise ProviderRateLimitError(f"Rate limited for model {model}")
                if response.status_code >= 500:
                    if attempt < self.max_retries:
                        await asyncio.sleep(self.retry_backoff_seconds * (2 ** attempt))
                        continue
                    raise ProviderResponseError(
                        f"Provider server error for model {model}: HTTP {response.status_code}"
                    )

                response.raise_for_status()

                data = response.json()
                if "choices" not in data or not data["choices"]:
                    raise ProviderResponseError(
                        f"Invalid response shape for model {model}: missing choices"
                    )
                message = data["choices"][0].get("message", {})

                content = message.get("content", "")
                if isinstance(content, list):
                    content = "".join(
                        part.get("text", "")
                        for part in content
                        if isinstance(part, dict)
                    )
                if content is None:
                    content = ""
                if not isinstance(content, str):
                    content = str(content)

                return ProviderResponse(
                    content=content,
                    reasoning_details=message.get("reasoning_details"),
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
                    await asyncio.sleep(self.retry_backoff_seconds * (2 ** attempt))
                    continue
                raise ProviderTimeoutError(f"Timeout querying model {model}") from exc
            except httpx.TransportError as exc:
                if attempt < self.max_retries:
                    await asyncio.sleep(self.retry_backoff_seconds * (2 ** attempt))
                    continue
                raise ProviderConnectionError(
                    f"Connection error querying model {model}"
                ) from exc
            except Exception as exc:
                raise ProviderResponseError(
                    f"Unhandled provider error for model {model}: {exc}"
                ) from exc

        raise ProviderResponseError(f"Exhausted retries for model {model}")
