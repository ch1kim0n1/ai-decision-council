"""Tests for the in-memory rate limiter (issue #24)."""

from __future__ import annotations

import pytest

from ai_decision_council.api.fastapi.rate_limiter import InMemoryRateLimiter


class TestInMemoryRateLimiter:
    @pytest.mark.asyncio
    async def test_allows_within_limits(self) -> None:
        limiter = InMemoryRateLimiter()
        allowed, reason = await limiter.acquire(
            ["k"], window_seconds=60, max_requests=5, max_concurrent=5
        )
        assert allowed is True
        assert reason is None
        await limiter.release(["k"])

    @pytest.mark.asyncio
    async def test_request_rate_exceeded(self) -> None:
        limiter = InMemoryRateLimiter()
        # max_concurrent high so only request-rate limit triggers.
        for _ in range(2):
            allowed, _ = await limiter.acquire(
                ["k"], window_seconds=60, max_requests=2, max_concurrent=100
            )
            assert allowed
            await limiter.release(["k"])
        allowed, reason = await limiter.acquire(
            ["k"], window_seconds=60, max_requests=2, max_concurrent=100
        )
        assert allowed is False
        assert reason == "request_rate_exceeded"

    @pytest.mark.asyncio
    async def test_concurrency_exceeded(self) -> None:
        limiter = InMemoryRateLimiter()
        # Hold two in-flight without releasing.
        await limiter.acquire(["k"], window_seconds=60, max_requests=100, max_concurrent=2)
        await limiter.acquire(["k"], window_seconds=60, max_requests=100, max_concurrent=2)
        allowed, reason = await limiter.acquire(
            ["k"], window_seconds=60, max_requests=100, max_concurrent=2
        )
        assert allowed is False
        assert reason == "concurrency_exceeded"

    @pytest.mark.asyncio
    async def test_release_frees_concurrency_slot(self) -> None:
        limiter = InMemoryRateLimiter()
        await limiter.acquire(["k"], window_seconds=60, max_requests=100, max_concurrent=1)
        blocked, reason = await limiter.acquire(
            ["k"], window_seconds=60, max_requests=100, max_concurrent=1
        )
        assert blocked is False
        assert reason == "concurrency_exceeded"
        await limiter.release(["k"])
        allowed, _ = await limiter.acquire(
            ["k"], window_seconds=60, max_requests=100, max_concurrent=1
        )
        assert allowed is True

    @pytest.mark.asyncio
    async def test_window_rollover_allows_again(self) -> None:
        limiter = InMemoryRateLimiter()
        allowed, _ = await limiter.acquire(
            ["k"], window_seconds=60, max_requests=1, max_concurrent=100
        )
        assert allowed
        await limiter.release(["k"])
        # Rewind the recorded timestamp beyond the window so it gets evicted.
        limiter._recent["k"][0] -= 120
        allowed, reason = await limiter.acquire(
            ["k"], window_seconds=60, max_requests=1, max_concurrent=100
        )
        assert allowed is True
        assert reason is None

    @pytest.mark.asyncio
    async def test_independent_keys(self) -> None:
        limiter = InMemoryRateLimiter()
        await limiter.acquire(["a"], window_seconds=60, max_requests=1, max_concurrent=1)
        # Different key is unaffected.
        allowed, _ = await limiter.acquire(
            ["b"], window_seconds=60, max_requests=1, max_concurrent=1
        )
        assert allowed is True
