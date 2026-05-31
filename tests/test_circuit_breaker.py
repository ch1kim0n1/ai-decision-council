"""Tests for the circuit breaker module (issue #24)."""

from __future__ import annotations

import pytest

from ai_decision_council.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerOpenError,
    CircuitState,
)


class _Boom(Exception):
    pass


class TestCircuitBreakerSync:
    def test_starts_closed(self) -> None:
        cb = CircuitBreaker()
        assert cb.is_closed
        assert cb.state == CircuitState.CLOSED

    def test_successful_call_returns_value(self) -> None:
        cb = CircuitBreaker()
        assert cb.call(lambda: 7) == 7
        assert cb.is_closed

    def test_opens_after_threshold(self) -> None:
        cb = CircuitBreaker(failure_threshold=3, expected_exception=_Boom)

        def _fail() -> None:
            raise _Boom()

        for _ in range(3):
            with pytest.raises(_Boom):
                cb.call(_fail)
        assert cb.is_open

    def test_open_circuit_fails_fast(self) -> None:
        cb = CircuitBreaker(failure_threshold=1, expected_exception=_Boom)
        with pytest.raises(_Boom):
            cb.call(lambda: (_ for _ in ()).throw(_Boom()))
        assert cb.is_open
        with pytest.raises(CircuitBreakerOpenError):
            cb.call(lambda: 1)

    def test_half_open_then_close_after_recovery(self) -> None:
        cb = CircuitBreaker(
            failure_threshold=1, recovery_timeout_seconds=60, expected_exception=_Boom
        )
        with pytest.raises(_Boom):
            cb.call(lambda: (_ for _ in ()).throw(_Boom()))
        assert cb.is_open
        # Simulate recovery window elapsing.
        cb.last_failure_time = cb.last_failure_time - 61  # type: ignore[operator]
        # First success transitions to HALF_OPEN and counts one success.
        assert cb.call(lambda: 1) == 1
        assert cb.is_half_open
        # Second success closes the circuit.
        assert cb.call(lambda: 2) == 2
        assert cb.is_closed

    def test_half_open_failure_reopens(self) -> None:
        cb = CircuitBreaker(
            failure_threshold=1, recovery_timeout_seconds=60, expected_exception=_Boom
        )
        with pytest.raises(_Boom):
            cb.call(lambda: (_ for _ in ()).throw(_Boom()))
        cb.last_failure_time = cb.last_failure_time - 61  # type: ignore[operator]
        # Enter half-open via a success.
        cb.call(lambda: 1)
        assert cb.is_half_open
        # A failure in half-open reopens immediately.
        with pytest.raises(_Boom):
            cb.call(lambda: (_ for _ in ()).throw(_Boom()))
        assert cb.is_open

    def test_reset(self) -> None:
        cb = CircuitBreaker(failure_threshold=1, expected_exception=_Boom)
        with pytest.raises(_Boom):
            cb.call(lambda: (_ for _ in ()).throw(_Boom()))
        cb.reset()
        assert cb.is_closed
        assert cb.failure_count == 0


class TestCircuitBreakerAsync:
    @pytest.mark.asyncio
    async def test_async_success(self) -> None:
        cb = CircuitBreaker()

        async def _ok() -> int:
            return 5

        assert await cb.call_async(_ok) == 5

    @pytest.mark.asyncio
    async def test_async_opens_and_fails_fast(self) -> None:
        cb = CircuitBreaker(failure_threshold=2, expected_exception=_Boom)

        async def _fail() -> None:
            raise _Boom()

        for _ in range(2):
            with pytest.raises(_Boom):
                await cb.call_async(_fail)
        assert cb.is_open
        with pytest.raises(CircuitBreakerOpenError):
            await cb.call_async(_fail)

    @pytest.mark.asyncio
    async def test_async_passes_args(self) -> None:
        cb = CircuitBreaker()

        async def _add(a: int, *, b: int) -> int:
            return a + b

        assert await cb.call_async(_add, 2, b=3) == 5
