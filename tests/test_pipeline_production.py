"""Regression tests for production features wired into the pipeline (issue #20).

Verifies that the response cache, cost/token metrics, and circuit breaker are
actually invoked by the council pipeline (previously dead code).
"""

from __future__ import annotations

from typing import Any, Dict, List
from unittest.mock import MagicMock

import pytest

from ai_decision_council.cache import ResponseCache
from ai_decision_council.circuit_breaker import CircuitBreaker
from ai_decision_council.client import Council
from ai_decision_council.config import CouncilConfig
from ai_decision_council.council import run_full_council_with_runtime
from ai_decision_council.providers.base import ProviderError, ProviderResponse

TWO_MODELS = ["openai/gpt-4o", "anthropic/claude-3-haiku"]


def _make_config(**kw: Any) -> CouncilConfig:
    defaults: Dict[str, Any] = {"api_key": "k", "models": TWO_MODELS}
    defaults.update(kw)
    return CouncilConfig(**defaults).with_resolved_defaults()


def _ranked(labels: list[str]) -> str:
    lines = "\n".join(f"{i + 1}. {label}" for i, label in enumerate(labels))
    return f"Evaluation text.\n\nFINAL RANKING:\n{lines}"


def _counting_adapter(usage: dict | None = None) -> tuple[MagicMock, list[int]]:
    """Adapter that counts chat calls and returns ranking-aware responses."""
    count = [0]

    async def _chat(model: str, messages: List[Dict[str, str]], timeout: float) -> ProviderResponse:
        count[0] += 1
        text = messages[0]["content"]
        if "FINAL RANKING" in text or "evaluating different responses" in text:
            content = _ranked(["Response A", "Response B"])
        else:
            content = "An answer."
        raw = {"usage": usage} if usage else None
        return ProviderResponse(content=content, raw=raw)

    adapter = MagicMock()
    adapter.chat = _chat
    return adapter, count


class TestCacheShortCircuit:
    @pytest.mark.asyncio
    async def test_repeated_run_uses_cache(self) -> None:
        cfg = _make_config()
        adapter, count = _counting_adapter()
        cache = ResponseCache()

        s1, *_ , meta1 = await run_full_council_with_runtime(
            "same prompt", config=cfg, adapter=adapter, cache=cache
        )
        calls_after_first = count[0]
        assert calls_after_first > 0
        assert meta1["cached"] is False

        # Second identical run must hit the cache (no new provider calls).
        _s1, _s2, _s3, meta2 = await run_full_council_with_runtime(
            "same prompt", config=cfg, adapter=adapter, cache=cache
        )
        assert count[0] == calls_after_first
        assert meta2["cached"] is True

    @pytest.mark.asyncio
    async def test_disabled_cache_does_not_short_circuit(self) -> None:
        cfg = _make_config()
        adapter, count = _counting_adapter()
        cache = ResponseCache(enabled=False)
        await run_full_council_with_runtime("p", config=cfg, adapter=adapter, cache=cache)
        first = count[0]
        await run_full_council_with_runtime("p", config=cfg, adapter=adapter, cache=cache)
        assert count[0] > first


class TestMetricsInMetadata:
    @pytest.mark.asyncio
    async def test_metrics_populated_with_usage(self) -> None:
        cfg = _make_config(models=["gpt-4o", "gpt-4o-mini"], chairman_model="gpt-4o")
        usage = {"prompt_tokens": 1000, "completion_tokens": 500}
        adapter, _ = _counting_adapter(usage=usage)

        *_ , meta = await run_full_council_with_runtime("q", config=cfg, adapter=adapter)
        metrics = meta["metrics"]
        assert metrics["total_tokens"] > 0
        assert metrics["total_cost_usd"] > 0
        assert "cost_breakdown" in metrics

    @pytest.mark.asyncio
    async def test_metrics_present_even_without_usage(self) -> None:
        cfg = _make_config()
        adapter, _ = _counting_adapter(usage=None)
        *_ , meta = await run_full_council_with_runtime("q", config=cfg, adapter=adapter)
        assert "metrics" in meta
        # No usage -> zero cost, still no crash.
        assert meta["metrics"]["total_cost_usd"] == 0.0


class TestCircuitBreakerTrips:
    @pytest.mark.asyncio
    async def test_failing_provider_trips_breaker(self) -> None:
        cfg = _make_config(models=TWO_MODELS)

        async def _always_fail(model: str, messages: Any, timeout: float) -> ProviderResponse:
            raise ProviderError("provider down")

        adapter = MagicMock()
        adapter.chat = _always_fail

        # Low threshold so the breaker opens during the first run's stage 1.
        breaker = CircuitBreaker(failure_threshold=2, expected_exception=ProviderError)

        await run_full_council_with_runtime(
            "q", config=cfg, adapter=adapter, circuit_breaker=breaker
        )
        # After >= threshold failures the breaker is open.
        assert breaker.is_open

        # A subsequent run now fails fast via the open circuit rather than
        # re-hitting the failing provider.
        _s1, _s2, stage3, meta = await run_full_council_with_runtime(
            "q2", config=cfg, adapter=adapter, circuit_breaker=breaker
        )
        codes = {e["error_code"] for e in meta["errors"]}
        assert "circuit_open" in codes
        assert "error" in stage3.get("model", "").lower()


class TestCouncilClientWiring:
    @pytest.mark.asyncio
    async def test_client_has_default_breaker(self) -> None:
        cfg = _make_config()
        adapter, _ = _counting_adapter()
        council = Council(config=cfg, provider_adapter=adapter)
        assert council.circuit_breaker is not None

    @pytest.mark.asyncio
    async def test_client_can_disable_breaker(self) -> None:
        cfg = _make_config()
        adapter, _ = _counting_adapter()
        council = Council(config=cfg, provider_adapter=adapter, circuit_breaker=False)
        assert council.circuit_breaker is None

    @pytest.mark.asyncio
    async def test_client_cache_short_circuits(self) -> None:
        cfg = _make_config()
        adapter, count = _counting_adapter()
        council = Council(config=cfg, provider_adapter=adapter, cache=ResponseCache())
        await council.run("hello")
        first = count[0]
        result = await council.run("hello")
        assert count[0] == first
        assert result.metadata["cached"] is True
