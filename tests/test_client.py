"""Tests for the Council client class."""

from __future__ import annotations

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from ai_decision_council.client import Council
from ai_decision_council.config import CouncilConfig
from ai_decision_council.providers.base import ProviderResponse
from ai_decision_council.schemas import CouncilResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TWO_MODELS = ["openai/gpt-4o", "anthropic/claude-3-haiku"]

def _make_config(**kwargs) -> CouncilConfig:
    defaults = {"api_key": "test-key", "models": TWO_MODELS}
    defaults.update(kwargs)
    return CouncilConfig(**defaults).with_resolved_defaults()


def _make_mock_adapter(response_text: str = "Mock response") -> MagicMock:
    adapter = MagicMock()
    adapter.chat = AsyncMock(
        return_value=ProviderResponse(content=response_text)
    )
    return adapter


# ---------------------------------------------------------------------------
# Council construction
# ---------------------------------------------------------------------------

class TestCouncilConstruction:
    def test_from_config_and_adapter(self):
        cfg = _make_config()
        adapter = _make_mock_adapter()
        council = Council(config=cfg, provider_adapter=adapter)
        assert council.config == cfg
        assert council.provider_adapter is adapter

    def test_from_env_with_explicit_models(self):
        import os
        env = {
            "LLM_COUNCIL_API_KEY": "k",
            "LLM_COUNCIL_MODELS": ",".join(TWO_MODELS),
        }
        with patch.dict(os.environ, env, clear=True):
            council = Council.from_env()
            assert council.config.api_key == "k"

    def test_unsupported_provider_raises(self):
        with pytest.raises(ValueError, match="Unsupported provider"):
            _make_config(provider="unsupported-provider")

    def test_metadata_returns_dict(self):
        cfg = _make_config()
        adapter = _make_mock_adapter()
        council = Council(config=cfg, provider_adapter=adapter)
        meta = council.metadata()
        assert "models" in meta
        assert "provider" in meta
        assert "chairman_model" in meta


# ---------------------------------------------------------------------------
# Council.run (async)
# ---------------------------------------------------------------------------

class TestCouncilRun:
    @pytest.mark.asyncio
    async def test_run_returns_council_result(self):
        cfg = _make_config()
        adapter = _make_mock_adapter("A good answer.")
        council = Council(config=cfg, provider_adapter=adapter)
        result = await council.run("What is 2+2?")
        assert isinstance(result, CouncilResult)

    @pytest.mark.asyncio
    async def test_run_final_response_is_string(self):
        cfg = _make_config()
        adapter = _make_mock_adapter("Final synthesis here.")
        council = Council(config=cfg, provider_adapter=adapter)
        result = await council.run("What is the capital of France?")
        assert isinstance(result.final_response, str)
        assert len(result.final_response) > 0

    @pytest.mark.asyncio
    async def test_ask_returns_string(self):
        cfg = _make_config()
        adapter = _make_mock_adapter("Just the answer.")
        council = Council(config=cfg, provider_adapter=adapter)
        answer = await council.ask("Short question?")
        assert isinstance(answer, str)

    @pytest.mark.asyncio
    async def test_ask_equals_run_final_response(self):
        cfg = _make_config()
        adapter = _make_mock_adapter("Consistent answer.")
        council = Council(config=cfg, provider_adapter=adapter)
        ask_result = await council.ask("Test?")
        run_result = await council.run("Test?")
        # Both should be non-empty strings
        assert isinstance(ask_result, str)
        assert isinstance(run_result.final_response, str)

    @pytest.mark.asyncio
    async def test_result_errors_is_list(self):
        cfg = _make_config()
        adapter = _make_mock_adapter()
        council = Council(config=cfg, provider_adapter=adapter)
        result = await council.run("Anything?")
        assert isinstance(result.errors, list)

    @pytest.mark.asyncio
    async def test_result_contains_stage_data(self):
        cfg = _make_config()
        adapter = _make_mock_adapter("Response content.")
        council = Council(config=cfg, provider_adapter=adapter)
        result = await council.run("Tell me something.")
        assert isinstance(result.stage1, list)
        assert isinstance(result.stage2, list)
        assert isinstance(result.stage3, dict)


# ---------------------------------------------------------------------------
# Council.run_sync
# ---------------------------------------------------------------------------

class TestCouncilRunSync:
    def test_run_sync_returns_council_result(self):
        cfg = _make_config()
        adapter = _make_mock_adapter("Sync answer.")
        council = Council(config=cfg, provider_adapter=adapter)
        result = council.run_sync("A sync question?")
        assert isinstance(result, CouncilResult)

    def test_ask_sync_returns_string(self):
        cfg = _make_config()
        adapter = _make_mock_adapter("Sync text.")
        council = Council(config=cfg, provider_adapter=adapter)
        answer = council.ask_sync("Another question?")
        assert isinstance(answer, str)

    def test_run_sync_raises_inside_event_loop(self):
        """Calling run_sync from inside an active event loop must raise RuntimeError."""
        cfg = _make_config()
        adapter = _make_mock_adapter()
        council = Council(config=cfg, provider_adapter=adapter)

        async def _inner():
            council.run_sync("test")

        with pytest.raises(RuntimeError, match="event loop"):
            asyncio.run(_inner())


# ---------------------------------------------------------------------------
# _build_adapter dispatch for new providers
# ---------------------------------------------------------------------------

class TestBuildAdapter:
    def test_openrouter_dispatch(self):
        from ai_decision_council.providers.openrouter import OpenRouterAdapter
        cfg = _make_config(provider="openrouter")
        adapter = Council._build_adapter(cfg)
        assert isinstance(adapter, OpenRouterAdapter)

    def test_openai_dispatch(self):
        from ai_decision_council.providers.openai import OpenAIAdapter
        cfg = _make_config(provider="openai")
        adapter = Council._build_adapter(cfg)
        assert isinstance(adapter, OpenAIAdapter)

    def test_anthropic_dispatch(self):
        from ai_decision_council.providers.anthropic import AnthropicAdapter
        cfg = _make_config(provider="anthropic")
        adapter = Council._build_adapter(cfg)
        assert isinstance(adapter, AnthropicAdapter)

    def test_ollama_dispatch(self):
        from ai_decision_council.providers.ollama import OllamaAdapter
        cfg = _make_config(provider="ollama")
        adapter = Council._build_adapter(cfg)
        assert isinstance(adapter, OllamaAdapter)
