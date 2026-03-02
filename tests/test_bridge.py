"""Tests for CouncilBridge (backward-compat wrapper)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from ai_decision_council.bridge import CouncilBridge
from ai_decision_council.config import CouncilConfig
from ai_decision_council.providers.base import ProviderResponse
from ai_decision_council.schemas import CouncilResult

TWO_MODELS = ["openai/gpt-4o", "anthropic/claude-3-haiku"]


def _make_config() -> CouncilConfig:
    return CouncilConfig(api_key="k", models=TWO_MODELS).with_resolved_defaults()


def _make_adapter(content: str = "Bridge answer") -> MagicMock:
    adapter = MagicMock()
    adapter.chat = AsyncMock(return_value=ProviderResponse(content=content))
    return adapter


class TestCouncilBridgeDelegation:
    """CouncilBridge must delegate faithfully to the underlying Council."""

    @pytest.mark.asyncio
    async def test_run_returns_council_result(self):
        bridge = CouncilBridge(config=_make_config(), provider_adapter=_make_adapter())
        result = await bridge.run("What is Python?")
        assert isinstance(result, CouncilResult)

    @pytest.mark.asyncio
    async def test_ask_returns_string(self):
        bridge = CouncilBridge(config=_make_config(), provider_adapter=_make_adapter())
        answer = await bridge.ask("What is Python?")
        assert isinstance(answer, str)

    def test_run_sync_returns_council_result(self):
        bridge = CouncilBridge(config=_make_config(), provider_adapter=_make_adapter())
        result = bridge.run_sync("Sync question?")
        assert isinstance(result, CouncilResult)

    def test_ask_sync_returns_string(self):
        bridge = CouncilBridge(config=_make_config(), provider_adapter=_make_adapter())
        answer = bridge.ask_sync("Sync question?")
        assert isinstance(answer, str)

    @pytest.mark.asyncio
    async def test_run_and_ask_consistent(self):
        bridge = CouncilBridge(config=_make_config(), provider_adapter=_make_adapter())
        result = await bridge.run("Same question?")
        answer = await bridge.ask("Same question?")
        # Both should return non-empty outputs
        assert isinstance(result.final_response, str)
        assert isinstance(answer, str)
