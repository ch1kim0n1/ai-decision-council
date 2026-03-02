"""Response caching with TTL and optional Redis support."""

from __future__ import annotations

import hashlib
import json
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, Generic, Optional, TypeVar

T = TypeVar("T")


class CacheBackend(ABC, Generic[T]):
    """Abstract cache backend interface."""

    @abstractmethod
    def get(self, key: str) -> T | None:
        """Retrieve value from cache."""
        pass

    @abstractmethod
    def set(self, key: str, value: T, ttl_seconds: int | None = None) -> None:
        """Store value in cache with optional TTL."""
        pass

    @abstractmethod
    def delete(self, key: str) -> None:
        """Delete key from cache."""
        pass

    @abstractmethod
    def clear(self) -> None:
        """Clear all cached values."""
        pass


class InMemoryCache(CacheBackend[T]):
    """Simple in-memory cache with TTL support."""

    def __init__(self) -> None:
        self._cache: dict[str, tuple[T, float | None]] = {}

    def get(self, key: str) -> T | None:
        """Retrieve value from cache, checking TTL."""
        if key not in self._cache:
            return None

        value, expiry = self._cache[key]
        if expiry is not None and time.time() > expiry:
            del self._cache[key]
            return None

        return value

    def set(self, key: str, value: T, ttl_seconds: int | None = None) -> None:
        """Store value with optional TTL."""
        expiry = None
        if ttl_seconds is not None:
            expiry = time.time() + ttl_seconds
        self._cache[key] = (value, expiry)

    def delete(self, key: str) -> None:
        """Delete key from cache."""
        self._cache.pop(key, None)

    def clear(self) -> None:
        """Clear all cached values."""
        self._cache.clear()

    def size(self) -> int:
        """Return number of cached items."""
        # Clean expired items first
        now = time.time()
        expired = [k for k, (_, exp) in self._cache.items() if exp and now > exp]
        for k in expired:
            del self._cache[k]
        return len(self._cache)


class RedisCache(CacheBackend[T]):
    """Redis-backed cache with TTL support."""

    def __init__(self, host: str = "localhost", port: int = 6379, db: int = 0) -> None:
        try:
            import redis
        except ImportError:
            raise ImportError("redis package required for RedisCache. Install with: pip install redis")

        self.client = redis.Redis(host=host, port=port, db=db, decode_responses=True)

    def get(self, key: str) -> T | None:
        """Retrieve value from Redis."""
        value = self.client.get(key)
        if value is None:
            return None
        try:
            return json.loads(value)  # type: ignore[return-value]
        except (json.JSONDecodeError, TypeError):
            return None

    def set(self, key: str, value: T, ttl_seconds: int | None = None) -> None:
        """Store value in Redis with optional TTL."""
        try:
            serialized = json.dumps(value, default=str)
            if ttl_seconds:
                self.client.setex(key, ttl_seconds, serialized)
            else:
                self.client.set(key, serialized)
        except (TypeError, json.JSONEncodeError):
            pass  # Skip caching if not serializable

    def delete(self, key: str) -> None:
        """Delete key from Redis."""
        self.client.delete(key)

    def clear(self) -> None:
        """Clear all keys from current database."""
        self.client.flushdb()


def compute_cache_key(
    query: str,
    models: list[str],
    provider: str,
    additional_params: dict[str, Any] | None = None,
) -> str:
    """Compute deterministic cache key from query and parameters.

    Parameters
    ----------
    query : str
        User query/prompt.
    models : list[str]
        List of models used.
    provider : str
        Provider name.
    additional_params : dict[str, Any] | None
        Additional parameters affecting output (chairman_model, etc.).

    Returns
    -------
    str
        SHA256 hash of normalized parameters.
    """
    params = {
        "query": query,
        "models": sorted(models),
        "provider": provider,
        **(additional_params or {}),
    }
    key_str = json.dumps(params, sort_keys=True, default=str)
    return hashlib.sha256(key_str.encode()).hexdigest()


class ResponseCache:
    """High-level cache wrapper for council responses."""

    def __init__(
        self,
        backend: CacheBackend[Any] | None = None,
        default_ttl_seconds: int = 3600,
        enabled: bool = True,
    ) -> None:
        self.backend = backend or InMemoryCache()
        self.default_ttl_seconds = default_ttl_seconds
        self.enabled = enabled

    def get(self, key: str) -> Any | None:
        """Retrieve cached response."""
        if not self.enabled:
            return None
        return self.backend.get(key)

    def set(
        self,
        key: str,
        value: Any,
        ttl_seconds: int | None = None,
    ) -> None:
        """Cache a response."""
        if not self.enabled:
            return
        ttl = ttl_seconds or self.default_ttl_seconds
        self.backend.set(key, value, ttl)

    def delete(self, key: str) -> None:
        """Delete cached response."""
        self.backend.delete(key)

    def clear(self) -> None:
        """Clear entire cache."""
        self.backend.clear()
