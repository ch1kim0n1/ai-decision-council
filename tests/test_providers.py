"""Tests for the OpenRouter provider adapter."""

from __future__ import annotations

import json
import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock, patch

from ai_decision_council.providers.base import (
    ProviderAuthError,
    ProviderConfigError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderTimeoutError,
    ProviderConnectionError,
    ProviderResponse,
    ProviderError,
)
from ai_decision_council.providers.openrouter import OpenRouterAdapter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_adapter(**kwargs) -> OpenRouterAdapter:
    defaults = {
        "api_key": "test-key",
        "api_url": "https://openrouter.ai/api/v1/chat/completions",
        "max_retries": 0,
        "retry_backoff_seconds": 0.0,
    }
    defaults.update(kwargs)
    return OpenRouterAdapter(**defaults)


def _ok_response_payload(content: str = "Hello!") -> dict:
    return {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": content,
                    "reasoning_details": None,
                }
            }
        ]
    }


def _mock_http_response(status_code: int, payload: dict | None = None) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    body = json.dumps(payload or {}).encode()
    resp.content = body
    resp.json.return_value = payload or {}
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "error", request=MagicMock(), response=resp
        )
    return resp


# ---------------------------------------------------------------------------
# Provider base error hierarchy
# ---------------------------------------------------------------------------

class TestProviderErrorHierarchy:
    def test_all_errors_inherit_provider_error(self):
        for cls in (
            ProviderAuthError,
            ProviderConfigError,
            ProviderRateLimitError,
            ProviderResponseError,
            ProviderTimeoutError,
            ProviderConnectionError,
        ):
            assert issubclass(cls, ProviderError)

    def test_each_has_distinct_code(self):
        codes = [
            ProviderAuthError.code,
            ProviderConfigError.code,
            ProviderRateLimitError.code,
            ProviderResponseError.code,
            ProviderTimeoutError.code,
            ProviderConnectionError.code,
        ]
        assert len(codes) == len(set(codes))

    def test_provider_response_dataclass(self):
        r = ProviderResponse(content="hi")
        assert r.content == "hi"
        assert r.reasoning_details is None
        assert r.raw is None


# ---------------------------------------------------------------------------
# OpenRouterAdapter.chat
# ---------------------------------------------------------------------------

class TestOpenRouterAdapterMissingConfig:
    @pytest.mark.asyncio
    async def test_missing_api_key_raises_config_error(self):
        adapter = _make_adapter(api_key=None)
        with pytest.raises(ProviderConfigError):
            await adapter.chat("m", [{"role": "user", "content": "hi"}], timeout=10)

    @pytest.mark.asyncio
    async def test_missing_api_url_raises_config_error(self):
        adapter = _make_adapter(api_url="")
        with pytest.raises(ProviderConfigError):
            await adapter.chat("m", [{"role": "user", "content": "hi"}], timeout=10)


class TestOpenRouterAdapterHTTPErrors:
    def _patch_client(self, response: MagicMock):
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=response)
        return patch("httpx.AsyncClient", return_value=mock_client)

    @pytest.mark.asyncio
    async def test_401_raises_auth_error(self):
        adapter = _make_adapter()
        resp = _mock_http_response(401)
        with self._patch_client(resp):
            with pytest.raises(ProviderAuthError):
                await adapter.chat("m", [{"role": "user", "content": "hi"}], timeout=10)

    @pytest.mark.asyncio
    async def test_403_raises_auth_error(self):
        adapter = _make_adapter()
        resp = _mock_http_response(403)
        with self._patch_client(resp):
            with pytest.raises(ProviderAuthError):
                await adapter.chat("m", [{"role": "user", "content": "hi"}], timeout=10)

    @pytest.mark.asyncio
    async def test_429_raises_rate_limit_error(self):
        adapter = _make_adapter(max_retries=0)
        resp = _mock_http_response(429)
        with self._patch_client(resp):
            with pytest.raises(ProviderRateLimitError):
                await adapter.chat("m", [{"role": "user", "content": "hi"}], timeout=10)

    @pytest.mark.asyncio
    async def test_500_raises_response_error(self):
        adapter = _make_adapter(max_retries=0)
        resp = _mock_http_response(500)
        with self._patch_client(resp):
            with pytest.raises(ProviderResponseError):
                await adapter.chat("m", [{"role": "user", "content": "hi"}], timeout=10)

    @pytest.mark.asyncio
    async def test_timeout_exception_raises_timeout_error(self):
        adapter = _make_adapter(max_retries=0)
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
        with patch("httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(ProviderTimeoutError):
                await adapter.chat("m", [{"role": "user", "content": "hi"}], timeout=10)

    @pytest.mark.asyncio
    async def test_transport_error_raises_connection_error(self):
        adapter = _make_adapter(max_retries=0)
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(
            side_effect=httpx.TransportError("transport error")
        )
        with patch("httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(ProviderConnectionError):
                await adapter.chat("m", [{"role": "user", "content": "hi"}], timeout=10)


class TestOpenRouterAdapterSuccess:
    def _patch_client(self, payload: dict):
        resp = _mock_http_response(200, payload)
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=resp)
        return patch("httpx.AsyncClient", return_value=mock_client)

    @pytest.mark.asyncio
    async def test_returns_provider_response(self):
        adapter = _make_adapter()
        payload = _ok_response_payload("Hello!")
        with self._patch_client(payload):
            result = await adapter.chat("m", [{"role": "user", "content": "hi"}], timeout=10)
        assert isinstance(result, ProviderResponse)
        assert result.content == "Hello!"

    @pytest.mark.asyncio
    async def test_missing_choices_raises_response_error(self):
        adapter = _make_adapter()
        with self._patch_client({"choices": []}):
            with pytest.raises(ProviderResponseError):
                await adapter.chat("m", [{"role": "user", "content": "hi"}], timeout=10)

    @pytest.mark.asyncio
    async def test_none_content_coerced_to_empty_string(self):
        adapter = _make_adapter()
        payload = {"choices": [{"message": {"role": "assistant", "content": None}}]}
        with self._patch_client(payload):
            result = await adapter.chat("m", [{"role": "user", "content": "hi"}], timeout=10)
        assert result.content == ""

    @pytest.mark.asyncio
    async def test_list_content_joined(self):
        adapter = _make_adapter()
        payload = {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": [{"text": "Hello"}, {"text": " world"}],
                    }
                }
            ]
        }
        with self._patch_client(payload):
            result = await adapter.chat("m", [{"role": "user", "content": "hi"}], timeout=10)
        assert result.content == "Hello world"
