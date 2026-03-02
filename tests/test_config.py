"""Tests for CouncilConfig environment parsing, validation, and defaults."""

from __future__ import annotations

import os
import pytest
from unittest.mock import patch

from ai_decision_council.config import (
    CouncilConfig,
    SUPPORTED_PROVIDERS,
    _split_models,
    _env_int,
    _env_float,
)
from ai_decision_council.models import DEFAULT_MODEL_COUNT, MIN_MODELS, MAX_MODELS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class TestSplitModels:
    def test_basic_split(self):
        result = _split_models("a/model1,b/model2,c/model3")
        assert result == ["a/model1", "b/model2", "c/model3"]

    def test_strips_whitespace(self):
        result = _split_models("  a/model1 ,  b/model2  ")
        assert result == ["a/model1", "b/model2"]

    def test_filters_empty_segments(self):
        result = _split_models("a/model1,,b/model2,")
        assert result == ["a/model1", "b/model2"]

    def test_single_model(self):
        result = _split_models("openai/gpt-4o")
        assert result == ["openai/gpt-4o"]


class TestEnvInt:
    def test_returns_default_when_unset(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("_TEST_INT_VAR", None)
            assert _env_int("_TEST_INT_VAR", 42) == 42

    def test_returns_parsed_value(self):
        with patch.dict(os.environ, {"_TEST_INT_VAR": "7"}):
            assert _env_int("_TEST_INT_VAR", 42) == 7

    def test_raises_on_non_integer(self):
        with patch.dict(os.environ, {"_TEST_INT_VAR": "not_a_number"}):
            with pytest.raises(ValueError, match="must be an integer"):
                _env_int("_TEST_INT_VAR", 42)


class TestEnvFloat:
    def test_returns_default_when_unset(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("_TEST_FLOAT_VAR", None)
            assert _env_float("_TEST_FLOAT_VAR", 1.5) == 1.5

    def test_returns_parsed_value(self):
        with patch.dict(os.environ, {"_TEST_FLOAT_VAR": "2.75"}):
            assert _env_float("_TEST_FLOAT_VAR", 1.5) == 2.75

    def test_raises_on_non_float(self):
        with patch.dict(os.environ, {"_TEST_FLOAT_VAR": "bad"}):
            with pytest.raises(ValueError, match="must be a number"):
                _env_float("_TEST_FLOAT_VAR", 1.5)


# ---------------------------------------------------------------------------
# CouncilConfig construction
# ---------------------------------------------------------------------------

MINIMAL_MODELS = ["openai/gpt-4o", "anthropic/claude-3-haiku"]


class TestCouncilConfigDefaults:
    def _make_config(self, **kwargs) -> CouncilConfig:
        base = {
            "api_key": "test-key",
            "models": MINIMAL_MODELS,
        }
        base.update(kwargs)
        return CouncilConfig(**base).with_resolved_defaults()

    def test_chairman_defaults_to_first_model(self):
        cfg = self._make_config()
        assert cfg.chairman_model == MINIMAL_MODELS[0]

    def test_title_model_defaults_to_chairman(self):
        cfg = self._make_config()
        assert cfg.title_model == cfg.chairman_model

    def test_explicit_chairman_accepted(self):
        cfg = self._make_config(chairman_model=MINIMAL_MODELS[1])
        assert cfg.chairman_model == MINIMAL_MODELS[1]

    def test_explicit_title_model_accepted(self):
        cfg = self._make_config(title_model=MINIMAL_MODELS[1])
        assert cfg.title_model == MINIMAL_MODELS[1]

    def test_model_count_defaults(self):
        cfg = CouncilConfig(
            api_key="k", models=None, model_count=2
        ).with_resolved_defaults()
        assert len(cfg.models) == 2  # type: ignore[arg-type]

    def test_model_count_clamps_to_catalog(self):
        cfg = CouncilConfig(
            api_key="k", models=None, model_count=DEFAULT_MODEL_COUNT
        ).with_resolved_defaults()
        assert len(cfg.models) == DEFAULT_MODEL_COUNT  # type: ignore[arg-type]

    def test_frozen_config_is_immutable(self):
        cfg = self._make_config()
        with pytest.raises((AttributeError, TypeError)):
            cfg.api_key = "other"  # type: ignore[misc]


class TestCouncilConfigValidation:
    def _base_cfg(self, **kwargs):
        defaults = {"api_key": "k", "models": MINIMAL_MODELS}
        defaults.update(kwargs)
        return CouncilConfig(**defaults)

    def test_too_few_models_raises(self):
        with pytest.raises(ValueError, match="At least"):
            CouncilConfig(api_key="k", models=["single/model"]).with_resolved_defaults()

    def test_too_many_models_raises(self):
        too_many = [f"provider/model-{i}" for i in range(MAX_MODELS + 1)]
        with pytest.raises(ValueError, match="At most"):
            CouncilConfig(api_key="k", models=too_many).with_resolved_defaults()

    def test_chairman_not_in_models_raises(self):
        with pytest.raises(ValueError, match="chairman_model must be present"):
            CouncilConfig(
                api_key="k",
                models=MINIMAL_MODELS,
                chairman_model="other/model-not-in-list",
            ).with_resolved_defaults()

    def test_negative_retries_raises(self):
        with pytest.raises(ValueError, match="max_retries"):
            self._base_cfg(max_retries=-1).with_resolved_defaults()

    def test_zero_stage_timeout_raises(self):
        with pytest.raises(ValueError, match="stage_timeout_seconds"):
            self._base_cfg(stage_timeout_seconds=0).with_resolved_defaults()

    def test_zero_title_timeout_raises(self):
        with pytest.raises(ValueError, match="title_timeout_seconds"):
            self._base_cfg(title_timeout_seconds=0).with_resolved_defaults()

    def test_model_count_below_min_raises(self):
        with pytest.raises(ValueError):
            CouncilConfig(api_key="k", model_count=MIN_MODELS - 1).with_resolved_defaults()

    def test_model_count_above_max_raises(self):
        with pytest.raises(ValueError):
            CouncilConfig(api_key="k", model_count=MAX_MODELS + 1).with_resolved_defaults()


class TestCouncilConfigFromEnv:
    """Verify from_env correctly maps environment variables."""

    _base_env = {
        "LLM_COUNCIL_API_KEY": "env-key",
        "LLM_COUNCIL_MODELS": "openai/gpt-4o,anthropic/claude-3-haiku",
    }

    def test_reads_api_key(self):
        with patch.dict(os.environ, self._base_env, clear=True):
            cfg = CouncilConfig.from_env()
            assert cfg.api_key == "env-key"

    def test_fallback_openrouter_key(self):
        env = {
            "OPENROUTER_API_KEY": "or-key",
            "LLM_COUNCIL_MODELS": "openai/gpt-4o,anthropic/claude-3-haiku",
        }
        with patch.dict(os.environ, env, clear=True):
            cfg = CouncilConfig.from_env()
            assert cfg.api_key == "or-key"

    def test_reads_explicit_models(self):
        with patch.dict(os.environ, self._base_env, clear=True):
            cfg = CouncilConfig.from_env()
            assert "openai/gpt-4o" in (cfg.models or [])

    def test_reads_model_count(self):
        env = {"LLM_COUNCIL_API_KEY": "k", "LLM_COUNCIL_MODEL_COUNT": "2"}
        with patch.dict(os.environ, env, clear=True):
            cfg = CouncilConfig.from_env()
            assert len(cfg.models) == 2  # type: ignore[arg-type]

    def test_override_keyword_args(self):
        with patch.dict(os.environ, self._base_env, clear=True):
            cfg = CouncilConfig.from_env(api_key="overridden")
            assert cfg.api_key == "overridden"

    def test_reads_chairman_model(self):
        env = {**self._base_env, "LLM_COUNCIL_CHAIRMAN_MODEL": "openai/gpt-4o"}
        with patch.dict(os.environ, env, clear=True):
            cfg = CouncilConfig.from_env()
            assert cfg.chairman_model == "openai/gpt-4o"

    def test_reads_max_retries(self):
        env = {**self._base_env, "LLM_COUNCIL_MAX_RETRIES": "5"}
        with patch.dict(os.environ, env, clear=True):
            cfg = CouncilConfig.from_env()
            assert cfg.max_retries == 5

    def test_reads_stage_timeout(self):
        env = {**self._base_env, "LLM_COUNCIL_STAGE_TIMEOUT_SECONDS": "60"}
        with patch.dict(os.environ, env, clear=True):
            cfg = CouncilConfig.from_env()
            assert cfg.stage_timeout_seconds == 60.0


# ---------------------------------------------------------------------------
# Multi-provider support
# ---------------------------------------------------------------------------

class TestSupportedProviders:
    def test_supported_providers_tuple(self):
        assert "openrouter" in SUPPORTED_PROVIDERS
        assert "openai" in SUPPORTED_PROVIDERS
        assert "anthropic" in SUPPORTED_PROVIDERS
        assert "ollama" in SUPPORTED_PROVIDERS

    def test_unsupported_provider_raises(self):
        cfg = CouncilConfig(
            api_key="k",
            models=["openai/gpt-4o", "anthropic/claude-3-haiku"],
            provider="bad-provider",
        )
        with pytest.raises(ValueError, match="Unsupported provider"):
            cfg.with_resolved_defaults()

    def test_openai_provider_resolved(self):
        env = {
            "OPENAI_API_KEY": "sk-openai",
            "LLM_COUNCIL_PROVIDER": "openai",
            "LLM_COUNCIL_MODELS": "gpt-4o,gpt-4o-mini",
        }
        with patch.dict(os.environ, env, clear=True):
            cfg = CouncilConfig.from_env()
        assert cfg.api_key == "sk-openai"
        assert cfg.provider == "openai"
        assert "openai.com" in (cfg.api_url or "")

    def test_anthropic_provider_resolved(self):
        env = {
            "ANTHROPIC_API_KEY": "sk-ant-key",
            "LLM_COUNCIL_PROVIDER": "anthropic",
            "LLM_COUNCIL_MODELS": "claude-sonnet-4-5,claude-haiku-3-5",
        }
        with patch.dict(os.environ, env, clear=True):
            cfg = CouncilConfig.from_env()
        assert cfg.api_key == "sk-ant-key"
        assert cfg.provider == "anthropic"
        assert "anthropic" in (cfg.api_url or "")

    def test_ollama_provider_no_key_needed(self):
        env = {
            "LLM_COUNCIL_PROVIDER": "ollama",
            "LLM_COUNCIL_MODELS": "llama3.2,mistral",
        }
        with patch.dict(os.environ, env, clear=True):
            cfg = CouncilConfig.from_env()
        assert cfg.provider == "ollama"
        assert "localhost" in (cfg.api_url or "")

    def test_provider_specific_key_fallback(self):
        """When provider key is missing, falls back to LLM_COUNCIL_API_KEY."""
        env = {
            "LLM_COUNCIL_API_KEY": "generic-key",
            "LLM_COUNCIL_PROVIDER": "openai",
            "LLM_COUNCIL_MODELS": "gpt-4o,gpt-4o-mini",
        }
        with patch.dict(os.environ, env, clear=True):
            cfg = CouncilConfig.from_env()
        assert cfg.api_key == "generic-key"

    def test_explicit_api_url_overrides_default(self):
        env = {
            "LLM_COUNCIL_API_KEY": "k",
            "LLM_COUNCIL_PROVIDER": "openai",
            "LLM_COUNCIL_API_URL": "https://custom-proxy/v1/chat",
            "LLM_COUNCIL_MODELS": "gpt-4o,gpt-4o-mini",
        }
        with patch.dict(os.environ, env, clear=True):
            cfg = CouncilConfig.from_env()
        assert cfg.api_url == "https://custom-proxy/v1/chat"
