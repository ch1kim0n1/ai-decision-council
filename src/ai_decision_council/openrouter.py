"""Backward-compatible OpenRouter module shim."""

from typing import Any, Dict, List, Optional

from .config import CouncilConfig
from .providers.base import ProviderAdapter, ProviderError
from .providers.openrouter import OpenRouterAdapter


def _build_default_adapter(config: CouncilConfig) -> ProviderAdapter:
    return OpenRouterAdapter(
        api_key=config.api_key,
        api_url=config.api_url,
        max_retries=config.max_retries,
        retry_backoff_seconds=config.retry_backoff_seconds,
    )


async def query_model(
    model: str,
    messages: List[Dict[str, str]],
    timeout: float = 120.0,
    config: CouncilConfig | None = None,
    adapter: ProviderAdapter | None = None,
) -> Optional[Dict[str, Any]]:
    """
    Backward-compatible single-model query helper.

    Returns legacy dict shape for existing integrations.
    """
    config = (config or CouncilConfig.from_env()).with_resolved_defaults()
    adapter = adapter or _build_default_adapter(config)

    try:
        response = await adapter.chat(model=model, messages=messages, timeout=timeout)
        return {
            "content": response.content,
            "reasoning_details": response.reasoning_details,
        }
    except ProviderError as exc:
        print(f"Error querying model {model}: {exc}")
        return None
    except Exception as exc:  # pragma: no cover - defensive
        print(f"Unexpected query error for model {model}: {exc}")
        return None


async def query_models_parallel(
    models: List[str],
    messages: List[Dict[str, str]],
    timeout: float = 120.0,
    config: CouncilConfig | None = None,
    adapter: ProviderAdapter | None = None,
) -> Dict[str, Optional[Dict[str, Any]]]:
    """Backward-compatible multi-model query helper."""
    import asyncio

    config = (config or CouncilConfig.from_env()).with_resolved_defaults()
    adapter = adapter or _build_default_adapter(config)

    tasks = [
        query_model(
            model=model,
            messages=messages,
            timeout=timeout,
            config=config,
            adapter=adapter,
        )
        for model in models
    ]
    responses = await asyncio.gather(*tasks)
    return {model: response for model, response in zip(models, responses)}
