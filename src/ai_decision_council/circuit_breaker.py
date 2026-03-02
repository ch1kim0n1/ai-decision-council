"""Circuit breaker pattern for resilient provider calls."""

from __future__ import annotations

import time
from enum import Enum
from typing import Any, Callable, TypeVar

T = TypeVar("T")


class CircuitState(Enum):
    """Circuit breaker state."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing if service recovered


class CircuitBreaker:
    """Circuit breaker for fault tolerance.

    Protects against repeated calls to failing services by:
    1. Detecting failure patterns (consecutive errors within threshold)
    2. Opening circuit to fail fast and prevent cascading failures
    3. Half-opening periodically to test if service recovered
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout_seconds: int = 60,
        expected_exception: type[Exception] = Exception,
    ) -> None:
        self.failure_threshold = failure_threshold
        self.recovery_timeout_seconds = recovery_timeout_seconds
        self.expected_exception = expected_exception

        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: float | None = None
        self.state = CircuitState.CLOSED

    @property
    def is_closed(self) -> bool:
        """Returns True if circuit is closed (normal operation)."""
        return self.state == CircuitState.CLOSED

    @property
    def is_open(self) -> bool:
        """Returns True if circuit is open (failing, rejecting requests)."""
        return self.state == CircuitState.OPEN

    @property
    def is_half_open(self) -> bool:
        """Returns True if circuit is half-open (testing recovery)."""
        return self.state == CircuitState.HALF_OPEN

    def call(self, func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        """Execute function within circuit breaker protection.

        Parameters
        ----------
        func : Callable
            Function to execute.
        *args : Any
            Positional arguments to pass to func.
        **kwargs : Any
            Keyword arguments to pass to func.

        Returns
        -------
        T
            Return value of func.

        Raises
        ------
        CircuitBreakerOpenError
            If circuit is open and won't allow the call.
        """
        if self.is_open:
            if self._should_attempt_reset():
                self.state = CircuitState.HALF_OPEN
                self.success_count = 0
            else:
                raise CircuitBreakerOpenError(
                    f"Circuit is open. Will retry in "
                    f"{self.recovery_timeout_seconds}s"
                )

        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except self.expected_exception:
            self._on_failure()
            raise

    def _on_success(self) -> None:
        """Handle successful call."""
        self.failure_count = 0

        if self.is_half_open:
            self.success_count += 1
            if self.success_count >= 2:  # Require 2 successes to close
                self.state = CircuitState.CLOSED
                self.success_count = 0

    def _on_failure(self) -> None:
        """Handle failed call."""
        self.failure_count += 1
        self.last_failure_time = time.time()

        if self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN

        if self.is_half_open:
            self.state = CircuitState.OPEN
            self.success_count = 0

    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt recovery."""
        if self.last_failure_time is None:
            return False
        return (time.time() - self.last_failure_time) >= self.recovery_timeout_seconds

    def reset(self) -> None:
        """Manually reset circuit breaker to closed state."""
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = None


class CircuitBreakerOpenError(Exception):
    """Raised when circuit breaker is open and rejecting requests."""

    pass
