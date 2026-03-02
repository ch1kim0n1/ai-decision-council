"""Configuration objects and environment parsing."""

from dataclasses import dataclass, replace
import os
from typing import List, Optional

from dotenv import load_dotenv

from .models import DEFAULT_MODEL_CATALOG, DEFAULT_MODEL_COUNT, MAX_MODELS, MIN_MODELS

load_dotenv()

# Providers known to this package.  A custom provider_adapter can still be
# injected directly into Council() regardless of this list.
SUPPORTED_PROVIDERS = ("openrouter", "openai", "anthropic", "ollama")

# Default API URLs per provider
_PROVIDER_DEFAULT_URLS: dict[str, str] = {
    "openrouter": "https://openrouter.ai/api/v1/chat/completions",
    "openai": "https://api.openai.com/v1/chat/completions",
    "anthropic": "https://api.anthropic.com/v1/messages",
    "ollama": "http://localhost:11434/v1/chat/completions",
}


def _split_models(raw_models: str) -> List[str]:
    return [model.strip() for model in raw_models.split(",") if model.strip()]


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"Environment variable {name} must be an integer") from exc


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(f"Environment variable {name} must be a number") from exc


@dataclass(frozen=True)
class CouncilConfig:
    """Runtime configuration for council execution."""

    api_key: Optional[str] = None
    api_url: str = "https://openrouter.ai/api/v1/chat/completions"
    models: Optional[List[str]] = None
    model_count: int = DEFAULT_MODEL_COUNT
    chairman_model: Optional[str] = None
    title_model: Optional[str] = None
    provider: str = "openrouter"
    max_retries: int = 2
    retry_backoff_seconds: float = 0.5
    stage_timeout_seconds: float = 120.0
    title_timeout_seconds: float = 30.0

    def with_resolved_defaults(self) -> "CouncilConfig":
        """Apply defaults and validate resolved configuration."""
        if self.models:
            resolved_models = [m for m in self.models if m]
        else:
            if self.model_count < MIN_MODELS or self.model_count > MAX_MODELS:
                raise ValueError(
                    f"model_count must be between {MIN_MODELS} and {MAX_MODELS}"
                )
            resolved_models = DEFAULT_MODEL_CATALOG[: self.model_count]

        if len(resolved_models) < MIN_MODELS:
            raise ValueError(
                f"At least {MIN_MODELS} models are required; got {len(resolved_models)}"
            )
        if len(resolved_models) > MAX_MODELS:
            raise ValueError(
                f"At most {MAX_MODELS} models are supported; got {len(resolved_models)}"
            )

        chairman_model = self.chairman_model or resolved_models[0]
        if chairman_model not in resolved_models:
            raise ValueError("chairman_model must be present in selected models")

        title_model = self.title_model or chairman_model

        if self.max_retries < 0:
            raise ValueError("max_retries must be >= 0")
        if self.retry_backoff_seconds < 0:
            raise ValueError("retry_backoff_seconds must be >= 0")
        if self.stage_timeout_seconds <= 0:
            raise ValueError("stage_timeout_seconds must be > 0")
        if self.title_timeout_seconds <= 0:
            raise ValueError("title_timeout_seconds must be > 0")

        if self.provider not in SUPPORTED_PROVIDERS:
            raise ValueError(
                f"Unsupported provider '{self.provider}'. "
                f"Supported: {', '.join(SUPPORTED_PROVIDERS)}.  "
                "You can also pass a custom provider_adapter to Council()."
            )

        return replace(
            self,
            models=resolved_models,
            chairman_model=chairman_model,
            title_model=title_model,
        )

    @classmethod
    def from_env(cls, **overrides) -> "CouncilConfig":
        """Build config from env, then apply explicit overrides."""
        raw_models = os.getenv("LLM_COUNCIL_MODELS")
        env_models = _split_models(raw_models) if raw_models else None

        provider = os.getenv("LLM_COUNCIL_PROVIDER", "openrouter")

        # Resolve API key: prefer LLM_COUNCIL_API_KEY, then provider-specific key
        _provider_key_env: dict[str, str] = {
            "openrouter": "OPENROUTER_API_KEY",
            "openai": "OPENAI_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
            "ollama": "",  # Ollama needs no key
        }
        fallback_key_name = _provider_key_env.get(provider, "")
        api_key = (
            os.getenv("LLM_COUNCIL_API_KEY")
            or (os.getenv(fallback_key_name) if fallback_key_name else None)
        )

        # Resolve default API URL based on provider
        default_url = _PROVIDER_DEFAULT_URLS.get(provider, "https://openrouter.ai/api/v1/chat/completions")

        config = cls(
            api_key=api_key,
            api_url=os.getenv("LLM_COUNCIL_API_URL", default_url),
            models=env_models,
            model_count=_env_int("LLM_COUNCIL_MODEL_COUNT", DEFAULT_MODEL_COUNT),
            chairman_model=os.getenv("LLM_COUNCIL_CHAIRMAN_MODEL"),
            title_model=os.getenv("LLM_COUNCIL_TITLE_MODEL"),
            provider=provider,
            max_retries=_env_int("LLM_COUNCIL_MAX_RETRIES", 2),
            retry_backoff_seconds=_env_float("LLM_COUNCIL_RETRY_BACKOFF_SECONDS", 0.5),
            stage_timeout_seconds=_env_float("LLM_COUNCIL_STAGE_TIMEOUT_SECONDS", 120.0),
            title_timeout_seconds=_env_float("LLM_COUNCIL_TITLE_TIMEOUT_SECONDS", 30.0),
        )
        if overrides:
            config = replace(config, **overrides)
        return config.with_resolved_defaults()


def _load_default_config() -> CouncilConfig:
    try:
        return CouncilConfig.from_env()
    except Exception:
        return CouncilConfig(
            api_key=os.getenv("LLM_COUNCIL_API_KEY") or os.getenv("OPENROUTER_API_KEY"),
            models=DEFAULT_MODEL_CATALOG[:DEFAULT_MODEL_COUNT],
            chairman_model=DEFAULT_MODEL_CATALOG[0],
            title_model=DEFAULT_MODEL_CATALOG[0],
        ).with_resolved_defaults()


_DEFAULT_CONFIG = _load_default_config()


