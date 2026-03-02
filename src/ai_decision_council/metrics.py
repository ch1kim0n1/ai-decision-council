"""Cost and performance metrics tracking for council executions."""

from __future__ import annotations

import dataclasses
import time
from typing import Any


# Approximate token costs (USD per 1M tokens) as of March 2026
# These are estimates and should be updated regularly
MODEL_COSTS = {
    # OpenRouter models (varies by provider)
    "openai/gpt-4o": {"input": 2.50, "output": 10.0},
    "openai/gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "openai/o1-mini": {"input": 3.0, "output": 12.0},
    "openai/o1": {"input": 15.0, "output": 60.0},
    "anthropic/claude-opus-4-5": {"input": 3.0, "output": 15.0},
    "anthropic/claude-sonnet-4-5": {"input": 3.0, "output": 15.0},
    "anthropic/claude-haiku-3-5": {"input": 0.80, "output": 4.0},
    "google/gemini-2.0-flash": {"input": 0.075, "output": 0.30},
    "google/gemini-2.0-pro": {"input": 1.25, "output": 5.00},
    "deepseek/deepseek-chat": {"input": 0.14, "output": 0.28},
    "x-ai/grok-3": {"input": 5.0, "output": 15.0},
    # Direct provider models
    "gpt-4o": {"input": 2.50, "output": 10.0},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "claude-opus-4-5": {"input": 3.0, "output": 15.0},
    "claude-sonnet-4-5": {"input": 3.0, "output": 15.0},
    "claude-haiku-3-5": {"input": 0.80, "output": 4.0},
}


@dataclasses.dataclass
class ModelMetrics:
    """Metrics for a single model invocation."""

    model: str
    start_time: float
    end_time: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    status: str = "pending"  # pending, success, error
    error_message: str | None = None

    @property
    def duration_ms(self) -> float:
        """Duration in milliseconds."""
        end = self.end_time or time.time()
        return (end - self.start_time) * 1000

    @property
    def total_tokens(self) -> int:
        """Total tokens (input + output)."""
        return (self.input_tokens or 0) + (self.output_tokens or 0)

    @property
    def cost_usd(self) -> float:
        """Estimated cost in USD."""
        if not self.input_tokens or not self.output_tokens:
            return 0.0

        costs = MODEL_COSTS.get(self.model, MODEL_COSTS.get("gpt-4o-mini", {}))
        if not costs:
            return 0.0

        input_cost = (self.input_tokens / 1_000_000) * costs.get("input", 0)
        output_cost = (self.output_tokens / 1_000_000) * costs.get("output", 0)
        return input_cost + output_cost

    def to_dict(self) -> dict[str, Any]:
        """Export metrics as dictionary."""
        return {
            "model": self.model,
            "duration_ms": round(self.duration_ms, 2),
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "cost_usd": round(self.cost_usd, 6),
            "status": self.status,
            "error_message": self.error_message,
        }


@dataclasses.dataclass
class ExecutionMetrics:
    """Metrics for a complete council execution."""

    query: str
    provider: str
    models: list[str]
    start_time: float
    end_time: float | None = None
    stage1_metrics: list[ModelMetrics] = dataclasses.field(default_factory=list)
    stage2_metrics: list[ModelMetrics] = dataclasses.field(default_factory=list)
    stage3_metrics: list[ModelMetrics] = dataclasses.field(default_factory=list)
    cached: bool = False
    cache_key: str | None = None

    @property
    def duration_ms(self) -> float:
        """Total execution duration in milliseconds."""
        end = self.end_time or time.time()
        return (end - self.start_time) * 1000

    @property
    def total_cost_usd(self) -> float:
        """Total cost across all stages."""
        all_metrics = self.stage1_metrics + self.stage2_metrics + self.stage3_metrics
        return sum(m.cost_usd for m in all_metrics)

    @property
    def total_tokens(self) -> int:
        """Total tokens across all stages."""
        all_metrics = self.stage1_metrics + self.stage2_metrics + self.stage3_metrics
        return sum(m.total_tokens for m in all_metrics)

    @property
    def stage1_cost(self) -> float:
        """Cost of stage 1 (collect responses)."""
        return sum(m.cost_usd for m in self.stage1_metrics)

    @property
    def stage2_cost(self) -> float:
        """Cost of stage 2 (collect rankings)."""
        return sum(m.cost_usd for m in self.stage2_metrics)

    @property
    def stage3_cost(self) -> float:
        """Cost of stage 3 (synthesize final)."""
        return sum(m.cost_usd for m in self.stage3_metrics)

    def to_dict(self) -> dict[str, Any]:
        """Export execution metrics as dictionary."""
        return {
            "duration_ms": round(self.duration_ms, 2),
            "cached": self.cached,
            "total_cost_usd": round(self.total_cost_usd, 6),
            "total_tokens": self.total_tokens,
            "cost_breakdown": {
                "stage1_usd": round(self.stage1_cost, 6),
                "stage2_usd": round(self.stage2_cost, 6),
                "stage3_usd": round(self.stage3_cost, 6),
            },
            "stage1_models": len(self.stage1_metrics),
            "stage2_models": len(self.stage2_metrics),
            "stage3_models": len(self.stage3_metrics),
        }
