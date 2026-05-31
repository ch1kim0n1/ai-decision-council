"""Tests for the metrics / cost-tracking module (issue #24)."""

from __future__ import annotations

import time

from ai_decision_council.metrics import (
    MODEL_COSTS,
    ExecutionMetrics,
    ModelMetrics,
)


class TestModelMetrics:
    def test_total_tokens(self) -> None:
        m = ModelMetrics(model="gpt-4o", start_time=0.0, input_tokens=10, output_tokens=5)
        assert m.total_tokens == 15

    def test_total_tokens_with_none(self) -> None:
        m = ModelMetrics(model="gpt-4o", start_time=0.0)
        assert m.total_tokens == 0

    def test_cost_zero_without_tokens(self) -> None:
        m = ModelMetrics(model="gpt-4o", start_time=0.0)
        assert m.cost_usd == 0.0

    def test_cost_computed_from_model_costs(self) -> None:
        costs = MODEL_COSTS["gpt-4o"]
        m = ModelMetrics(
            model="gpt-4o",
            start_time=0.0,
            input_tokens=1_000_000,
            output_tokens=1_000_000,
        )
        expected = costs["input"] + costs["output"]
        assert m.cost_usd == expected

    def test_unknown_model_falls_back(self) -> None:
        m = ModelMetrics(
            model="totally/unknown",
            start_time=0.0,
            input_tokens=1_000_000,
            output_tokens=1_000_000,
        )
        # Falls back to gpt-4o-mini pricing (non-zero) rather than crashing.
        assert m.cost_usd > 0

    def test_duration_ms_uses_end_time(self) -> None:
        m = ModelMetrics(model="x", start_time=1.0, end_time=2.0)
        assert m.duration_ms == 1000.0

    def test_to_dict_shape(self) -> None:
        m = ModelMetrics(
            model="gpt-4o", start_time=0.0, end_time=1.0, input_tokens=1, output_tokens=2
        )
        d = m.to_dict()
        assert d["model"] == "gpt-4o"
        assert d["total_tokens"] == 3
        assert "cost_usd" in d


class TestExecutionMetrics:
    def _metric(self, model: str, inp: int, out: int) -> ModelMetrics:
        return ModelMetrics(
            model=model, start_time=0.0, end_time=1.0, input_tokens=inp, output_tokens=out
        )

    def test_total_cost_sums_stages(self) -> None:
        em = ExecutionMetrics(
            query="q",
            provider="openrouter",
            models=["gpt-4o"],
            start_time=time.time(),
        )
        # Each metric needs both input and output tokens for cost to be counted.
        em.stage1_metrics.append(self._metric("gpt-4o", 1_000_000, 1_000_000))
        em.stage3_metrics.append(self._metric("gpt-4o", 1_000_000, 1_000_000))
        per_call = MODEL_COSTS["gpt-4o"]["input"] + MODEL_COSTS["gpt-4o"]["output"]
        assert em.total_cost_usd == per_call * 2

    def test_total_tokens(self) -> None:
        em = ExecutionMetrics(
            query="q", provider="p", models=[], start_time=time.time()
        )
        em.stage1_metrics.append(self._metric("gpt-4o", 3, 4))
        em.stage2_metrics.append(self._metric("gpt-4o", 1, 1))
        assert em.total_tokens == 9

    def test_to_dict_contains_breakdown(self) -> None:
        em = ExecutionMetrics(
            query="q",
            provider="p",
            models=["gpt-4o"],
            start_time=time.time(),
            end_time=time.time(),
        )
        em.stage1_metrics.append(self._metric("gpt-4o", 100, 100))
        d = em.to_dict()
        assert "cost_breakdown" in d
        assert "total_cost_usd" in d
        assert d["stage1_models"] == 1
        assert d["cached"] is False
