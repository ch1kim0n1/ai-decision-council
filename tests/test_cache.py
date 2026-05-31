"""Tests for the response cache module (issue #24)."""

from __future__ import annotations

import time

from ai_decision_council.cache import (
    InMemoryCache,
    ResponseCache,
    compute_cache_key,
)


class TestInMemoryCache:
    def test_set_and_get(self) -> None:
        cache: InMemoryCache[str] = InMemoryCache()
        cache.set("k", "v")
        assert cache.get("k") == "v"

    def test_missing_key_returns_none(self) -> None:
        cache: InMemoryCache[str] = InMemoryCache()
        assert cache.get("absent") is None

    def test_ttl_expiry(self) -> None:
        cache: InMemoryCache[str] = InMemoryCache()
        cache.set("k", "v", ttl_seconds=1)
        # Force expiry without sleeping by rewinding the stored expiry.
        value, _expiry = cache._cache["k"]
        cache._cache["k"] = (value, time.time() - 1)
        assert cache.get("k") is None
        # Expired entry is evicted on access.
        assert "k" not in cache._cache

    def test_no_ttl_never_expires(self) -> None:
        cache: InMemoryCache[str] = InMemoryCache()
        cache.set("k", "v", ttl_seconds=None)
        assert cache.get("k") == "v"

    def test_delete(self) -> None:
        cache: InMemoryCache[str] = InMemoryCache()
        cache.set("k", "v")
        cache.delete("k")
        assert cache.get("k") is None

    def test_clear(self) -> None:
        cache: InMemoryCache[str] = InMemoryCache()
        cache.set("a", "1")
        cache.set("b", "2")
        cache.clear()
        assert cache.size() == 0

    def test_size_cleans_expired(self) -> None:
        cache: InMemoryCache[str] = InMemoryCache()
        cache.set("live", "v")
        cache.set("dead", "v", ttl_seconds=1)
        value, _ = cache._cache["dead"]
        cache._cache["dead"] = (value, time.time() - 1)
        assert cache.size() == 1


class TestComputeCacheKey:
    def test_deterministic(self) -> None:
        k1 = compute_cache_key("q", ["a", "b"], "openrouter")
        k2 = compute_cache_key("q", ["a", "b"], "openrouter")
        assert k1 == k2

    def test_model_order_insensitive(self) -> None:
        k1 = compute_cache_key("q", ["a", "b"], "openrouter")
        k2 = compute_cache_key("q", ["b", "a"], "openrouter")
        assert k1 == k2

    def test_query_changes_key(self) -> None:
        assert compute_cache_key("q1", ["a"], "p") != compute_cache_key("q2", ["a"], "p")

    def test_additional_params_change_key(self) -> None:
        base = compute_cache_key("q", ["a"], "p")
        with_param = compute_cache_key("q", ["a"], "p", {"chairman_model": "a"})
        assert base != with_param


class TestResponseCache:
    def test_get_set_roundtrip(self) -> None:
        cache = ResponseCache()
        cache.set("k", {"answer": 42})
        assert cache.get("k") == {"answer": 42}

    def test_disabled_cache_returns_none(self) -> None:
        cache = ResponseCache(enabled=False)
        cache.set("k", "v")
        assert cache.get("k") is None

    def test_default_ttl_applied(self) -> None:
        backend: InMemoryCache = InMemoryCache()
        cache = ResponseCache(backend=backend, default_ttl_seconds=99)
        cache.set("k", "v")
        _value, expiry = backend._cache["k"]
        assert expiry is not None and expiry > time.time()

    def test_clear(self) -> None:
        cache = ResponseCache()
        cache.set("k", "v")
        cache.clear()
        assert cache.get("k") is None
