"""In-memory rate limiter for abuse protection."""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict, deque


class InMemoryRateLimiter:
    """Simple in-memory limiter for abuse protection."""

    def __init__(self):
        self._recent: dict[str, deque[float]] = defaultdict(deque)
        self._inflight: dict[str, int] = defaultdict(int)
        self._lock = asyncio.Lock()

    async def acquire(
        self,
        keys: list[str],
        *,
        window_seconds: int,
        max_requests: int,
        max_concurrent: int,
    ) -> tuple[bool, str | None]:
        now = time.monotonic()
        cutoff = now - window_seconds
        async with self._lock:
            for key in keys:
                recent = self._recent[key]
                while recent and recent[0] < cutoff:
                    recent.popleft()
                if len(recent) >= max_requests:
                    return False, "request_rate_exceeded"
                if self._inflight[key] >= max_concurrent:
                    return False, "concurrency_exceeded"

            for key in keys:
                self._recent[key].append(now)
                self._inflight[key] += 1
        return True, None

    async def release(self, keys: list[str]) -> None:
        async with self._lock:
            for key in keys:
                current = self._inflight.get(key, 0)
                if current <= 1:
                    self._inflight.pop(key, None)
                else:
                    self._inflight[key] = current - 1


