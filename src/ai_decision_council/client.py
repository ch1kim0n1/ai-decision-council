"""Primary SDK client for ai-decision-council."""

from __future__ import annotations

import asyncio
from typing import Any, Dict

from .config import CouncilConfig
from .council import run_full_council_with_runtime
from .observability import configure_logging, get_logger
from .providers.base import ProviderAdapter
from .providers.openrouter import OpenRouterAdapter
from .schemas import CouncilResult, ModelRunError

configure_logging()
_log = get_logger("client")


def _run_sync_coro(coro):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    coro.close()
    raise RuntimeError(
        "Cannot call sync methods inside an active event loop. "
        "Use async methods (`run` / `ask`) instead."
    )


class Council:
    """Canonical client API for package integrations."""

    def __init__(
        self,
        config: CouncilConfig | None = None,
        provider_adapter: ProviderAdapter | None = None,
    ):
        resolved_config = (config or CouncilConfig.from_env()).with_resolved_defaults()
        self.config = resolved_config

        if provider_adapter is not None:
            self.provider_adapter = provider_adapter
        else:
            self.provider_adapter = self._build_adapter(resolved_config)

    @staticmethod
    def _build_adapter(config: CouncilConfig) -> ProviderAdapter:
        """Instantiate the correct adapter from the resolved config."""
        provider = config.provider
        api_key = config.api_key
        api_url = config.api_url
        retries = config.max_retries
        backoff = config.retry_backoff_seconds

        if provider == "openrouter":
            return OpenRouterAdapter(
                api_key=api_key,
                api_url=api_url,
                max_retries=retries,
                retry_backoff_seconds=backoff,
            )
        if provider == "openai":
            from .providers.openai import OpenAIAdapter
            return OpenAIAdapter(
                api_key=api_key,
                api_url=api_url,
                max_retries=retries,
                retry_backoff_seconds=backoff,
            )
        if provider == "anthropic":
            from .providers.anthropic import AnthropicAdapter
            return AnthropicAdapter(
                api_key=api_key,
                api_url=api_url,
                max_retries=retries,
                retry_backoff_seconds=backoff,
            )
        if provider == "ollama":
            from .providers.ollama import OllamaAdapter
            return OllamaAdapter(
                api_key=api_key,
                api_url=api_url,
                max_retries=retries,
                retry_backoff_seconds=backoff,
            )
        raise ValueError(
            f"Unsupported provider '{provider}'. "
            "Provide a custom provider_adapter to Council() for custom integrations."
        )

    @classmethod
    def from_env(cls, **overrides) -> "Council":
        """Create Council instance from env with optional explicit overrides."""
        config = CouncilConfig.from_env(**overrides)
        return cls(config=config)

    async def run(self, prompt: str) -> CouncilResult:
        """Run full council pipeline and return structured result."""
        _log.info("council_run_start", prompt_len=len(prompt), provider=self.config.provider,
                  model_count=len(self.config.models or []))
        stage1, stage2, stage3, metadata = await run_full_council_with_runtime(
            user_query=prompt,
            config=self.config,
            adapter=self.provider_adapter,
        )

        raw_errors = metadata.get("errors", [])
        errors = []
        for item in raw_errors:
            if isinstance(item, dict):
                errors.append(
                    ModelRunError(
                        model=str(item.get("model", "")),
                        stage=str(item.get("stage", "")),
                        error_code=str(item.get("error_code", "")),
                        message=str(item.get("message", "")),
                    )
                )

        result = CouncilResult(
            stage1=stage1,
            stage2=stage2,
            stage3=stage3,
            metadata=metadata,
            errors=errors,
        )
        _log.info("council_run_complete", error_count=len(errors))
        return result

    async def ask(self, prompt: str) -> str:
        """Run pipeline and return only final synthesized response text."""
        result = await self.run(prompt)
        return result.final_response

    def run_sync(self, prompt: str) -> CouncilResult:
        """Sync wrapper around `run` for non-async apps."""
        return _run_sync_coro(self.run(prompt))

    def ask_sync(self, prompt: str) -> str:
        """Sync wrapper around `ask` for non-async apps."""
        return _run_sync_coro(self.ask(prompt))

    def metadata(self) -> Dict[str, Any]:
        """Expose resolved runtime metadata for diagnostics and logging."""
        return {
            "provider": self.config.provider,
            "models": list(self.config.models or []),
            "chairman_model": self.config.chairman_model,
            "title_model": self.config.title_model,
            "max_retries": self.config.max_retries,
        }
