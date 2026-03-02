"""Integration tests for the full 3-stage council pipeline using mock adapters.

These tests wire the real orchestration logic (council.py) with a mock
ProviderAdapter so no real HTTP calls are made.  They act as end-to-end
smoke tests for the complete pipeline path.
"""

from __future__ import annotations

from typing import Any, Dict, List
import pytest
from unittest.mock import MagicMock

from ai_decision_council.client import Council
from ai_decision_council.config import CouncilConfig
from ai_decision_council.council import (
    run_full_council,
)
from ai_decision_council.providers.base import ProviderError, ProviderResponse
from ai_decision_council.schemas import CouncilResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TWO_MODELS = ["openai/gpt-4o", "anthropic/claude-3-haiku"]
THREE_MODELS = ["openai/gpt-4o", "anthropic/claude-3-haiku", "google/gemini-flash"]


def _make_config(models=None, chairman=None) -> CouncilConfig:
    kw: Dict[str, Any] = {"api_key": "test-key", "models": models or TWO_MODELS}
    if chairman:
        kw["chairman_model"] = chairman
    return CouncilConfig(**kw).with_resolved_defaults()


def _ranked_response(responses: list[str]) -> str:
    """Build a valid FINAL RANKING response from list of label strings."""
    ranking_lines = "\n".join(f"{i + 1}. {r}" for i, r in enumerate(responses))
    return (
        "Each response has good points.\n\n"
        f"FINAL RANKING:\n{ranking_lines}"
    )


def _make_cycling_adapter(responses: list[str]) -> MagicMock:
    """
    Adapter that cycles through a list of responses in order.
    Stage1 uses normal text; stage2 uses ranking text.
    """
    call_count = [0]

    async def _chat(model: str, messages: List[Dict[str, str]], timeout: float) -> ProviderResponse:
        idx = call_count[0] % len(responses)
        call_count[0] += 1
        return ProviderResponse(content=responses[idx])

    adapter = MagicMock()
    adapter.chat = _chat
    return adapter


def _make_ranked_adapter(stage1_text: str = "Good answer.", num_models: int = 2) -> MagicMock:
    """
    Returns an adapter that alternates between stage1 answers and valid rankings.
    """
    labels = [f"Response {chr(65 + i)}" for i in range(num_models)]
    ranked = _ranked_response(labels)

    responses = [stage1_text] * num_models + [ranked] * num_models + ["Final synthesis."]
    return _make_cycling_adapter(responses)


# ---------------------------------------------------------------------------
# run_full_council integration tests
# ---------------------------------------------------------------------------

class TestRunFullCouncilPipeline:
    @pytest.mark.asyncio
    async def test_returns_four_tuple(self):
        cfg = _make_config()
        adapter = _make_ranked_adapter(num_models=2)
        result = await run_full_council(user_query="Test?", config=cfg, adapter=adapter)
        assert len(result) == 4
        stage1, stage2, stage3, metadata = result
        assert isinstance(stage1, list)
        assert isinstance(stage2, list)
        assert isinstance(stage3, dict)
        assert isinstance(metadata, dict)

    @pytest.mark.asyncio
    async def test_stage1_has_model_and_response(self):
        cfg = _make_config()
        adapter = _make_ranked_adapter(num_models=2)
        stage1, _, _, _ = await run_full_council("Question?", config=cfg, adapter=adapter)
        for item in stage1:
            assert "model" in item
            assert "response" in item

    @pytest.mark.asyncio
    async def test_stage2_has_model_and_ranking(self):
        cfg = _make_config()
        adapter = _make_ranked_adapter(num_models=2)
        _, stage2, _, _ = await run_full_council("Question?", config=cfg, adapter=adapter)
        for item in stage2:
            assert "model" in item
            assert "ranking" in item

    @pytest.mark.asyncio
    async def test_stage3_has_model_and_response(self):
        cfg = _make_config()
        adapter = _make_ranked_adapter(num_models=2)
        _, _, stage3, _ = await run_full_council("Question?", config=cfg, adapter=adapter)
        assert "model" in stage3
        assert "response" in stage3

    @pytest.mark.asyncio
    async def test_metadata_has_label_to_model(self):
        cfg = _make_config()
        adapter = _make_ranked_adapter(num_models=2)
        _, _, _, metadata = await run_full_council("Question?", config=cfg, adapter=adapter)
        assert "label_to_model" in metadata
        assert isinstance(metadata["label_to_model"], dict)

    @pytest.mark.asyncio
    async def test_metadata_errors_is_list(self):
        cfg = _make_config()
        adapter = _make_ranked_adapter(num_models=2)
        _, _, _, metadata = await run_full_council("Question?", config=cfg, adapter=adapter)
        assert "errors" in metadata
        assert isinstance(metadata["errors"], list)

    @pytest.mark.asyncio
    async def test_stage1_count_matches_model_count(self):
        cfg = _make_config(models=TWO_MODELS)
        adapter = _make_ranked_adapter(num_models=2)
        stage1, _, _, _ = await run_full_council("Question?", config=cfg, adapter=adapter)
        assert len(stage1) == 2

    @pytest.mark.asyncio
    async def test_three_models_pipeline(self):
        cfg = _make_config(models=THREE_MODELS)
        adapter = _make_ranked_adapter(num_models=3)
        stage1, stage2, stage3, meta = await run_full_council("Question?", config=cfg, adapter=adapter)
        assert len(stage1) == 3
        assert "response" in stage3


# ---------------------------------------------------------------------------
# Partial-failure handling
# ---------------------------------------------------------------------------

class TestPipelinePartialFailure:
    @pytest.mark.asyncio
    async def test_one_model_failure_still_returns_result(self):
        """Stage 1 partial failure: one model errors, rest succeed."""
        cfg = _make_config(models=THREE_MODELS)
        call_count = [0]

        async def _chat(model, messages, timeout):
            call_count[0] += 1
            if call_count[0] == 1:
                # First call fails
                raise ProviderError("Simulated failure")
            labels = ["Response A", "Response B", "Response C"]
            ranking = _ranked_response(labels)
            # Alternate between a plain answer and a ranking
            if call_count[0] <= 3:
                return ProviderResponse(content="A good answer.")
            return ProviderResponse(content=ranking)

        adapter = MagicMock()
        adapter.chat = _chat

        stage1, _, stage3, metadata = await run_full_council(
            "Question?", config=cfg, adapter=adapter
        )
        # At least some stage1 results should be present
        assert isinstance(stage1, list)
        assert isinstance(stage3, dict)

    @pytest.mark.asyncio
    async def test_all_models_fail_returns_error_stage3(self):
        """If all stage1 models fail, pipeline returns an error stage3 response."""
        cfg = _make_config()

        async def _chat(model, messages, timeout):
            raise ProviderError("All fail")

        adapter = MagicMock()
        adapter.chat = _chat

        stage1, stage2, stage3, metadata = await run_full_council(
            "Question?", config=cfg, adapter=adapter
        )
        assert stage1 == []
        assert stage2 == []
        assert "error" in stage3.get("model", "").lower() or "fail" in stage3.get("response", "").lower()


# ---------------------------------------------------------------------------
# Council client end-to-end
# ---------------------------------------------------------------------------

class TestCouncilClientEndToEnd:
    @pytest.mark.asyncio
    async def test_council_run_returns_council_result(self):
        cfg = _make_config()
        adapter = _make_ranked_adapter(num_models=2)
        council = Council(config=cfg, provider_adapter=adapter)
        result = await council.run("What is recursion?")
        assert isinstance(result, CouncilResult)
        assert isinstance(result.final_response, str)

    @pytest.mark.asyncio
    async def test_council_ask_returns_non_empty_string(self):
        cfg = _make_config()
        adapter = _make_ranked_adapter(num_models=2)
        council = Council(config=cfg, provider_adapter=adapter)
        answer = await council.ask("Explain async/await.")
        assert isinstance(answer, str)
        assert len(answer) > 0

    def test_council_run_sync(self):
        cfg = _make_config()
        adapter = _make_ranked_adapter(num_models=2)
        council = Council(config=cfg, provider_adapter=adapter)
        result = council.run_sync("Sync question?")
        assert isinstance(result, CouncilResult)

    def test_council_ask_sync(self):
        cfg = _make_config()
        adapter = _make_ranked_adapter(num_models=2)
        council = Council(config=cfg, provider_adapter=adapter)
        answer = council.ask_sync("Sync ask?")
        assert isinstance(answer, str)
