"""Tests for new provider adapters: OpenAI, Ollama, Anthropic."""

from __future__ import annotations

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from ai_decision_council.providers.anthropic import AnthropicAdapter
from ai_decision_council.providers.ollama import OllamaAdapter
from ai_decision_council.providers.openai import OpenAIAdapter
from ai_decision_council.providers.openrouter import OpenRouterAdapter
from ai_decision_council.providers.base import (
    ProviderAuthError,
    ProviderError,
    ProviderRateLimitError,
    ProviderResponse,
    ProviderTimeoutError,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_httpx_response(status_code: int, body: dict) -> MagicMock:
    response = MagicMock(spec=httpx.Response)
    response.status_code = status_code
    response.is_success = (200 <= status_code < 300)
    response.json = MagicMock(return_value=body)
    response.text = json.dumps(body)
    return response


OPENAI_CHAT_RESPONSE = {
    "choices": [{"message": {"content": "Hello from OpenAI"}}],
}

ANTHROPIC_CHAT_RESPONSE = {
    "content": [{"type": "text", "text": "Hello from Anthropic"}],
}


# ===========================================================================
# OpenAIAdapter
# ===========================================================================

class TestOpenAIAdapter:
    """OpenAI adapter inherits OpenRouterAdapter and points to OpenAI URL."""

    def test_is_subclass_of_openrouter(self):
        assert issubclass(OpenAIAdapter, OpenRouterAdapter)

    def test_default_url_is_openai(self):
        assert "openai.com" in OpenAIAdapter.DEFAULT_API_URL

    def test_constructor(self):
        adapter = OpenAIAdapter(api_key="sk-test")
        assert adapter.api_key == "sk-test"
        assert "openai.com" in adapter.api_url

    def test_custom_url_respected(self):
        adapter = OpenAIAdapter(api_key="k", api_url="https://my-proxy/v1/chat")
        assert adapter.api_url == "https://my-proxy/v1/chat"

    @pytest.mark.asyncio
    async def test_chat_success(self):
        adapter = OpenAIAdapter(api_key="sk-test")
        mock_resp = _mock_httpx_response(200, OPENAI_CHAT_RESPONSE)
        with patch("httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.post = AsyncMock(return_value=mock_resp)
            mock_cls.return_value = mock_client

            result = await adapter.chat(
                model="gpt-4o",
                messages=[{"role": "user", "content": "hi"}],
                timeout=30.0,
            )
        assert isinstance(result, ProviderResponse)
        assert result.content == "Hello from OpenAI"

    @pytest.mark.asyncio
    async def test_chat_auth_error(self):
        adapter = OpenAIAdapter(api_key="bad-key")
        mock_resp = _mock_httpx_response(401, {"error": {"message": "invalid key"}})
        with patch("httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.post = AsyncMock(return_value=mock_resp)
            mock_cls.return_value = mock_client

            with pytest.raises(ProviderAuthError):
                await adapter.chat(
                    model="gpt-4o",
                    messages=[{"role": "user", "content": "hi"}],
                    timeout=30.0,
                )


# ===========================================================================
# OllamaAdapter
# ===========================================================================

class TestOllamaAdapter:
    """Ollama adapter: local OpenAI-compatible server, no auth required."""

    def test_is_subclass_of_openrouter(self):
        assert issubclass(OllamaAdapter, OpenRouterAdapter)

    def test_default_url_is_localhost(self):
        assert "localhost" in OllamaAdapter.DEFAULT_API_URL

    def test_sentinel_api_key(self):
        adapter = OllamaAdapter(api_key=None)
        assert adapter.api_key == "ollama"

    def test_provided_api_key_overrides_sentinel(self):
        adapter = OllamaAdapter(api_key="custom-key")
        assert adapter.api_key == "custom-key"

    def test_custom_url(self):
        adapter = OllamaAdapter(api_key=None, api_url="http://gpu-box:11434/v1/chat/completions")
        assert "gpu-box" in adapter.api_url

    @pytest.mark.asyncio
    async def test_chat_success(self):
        adapter = OllamaAdapter(api_key=None)
        mock_resp = _mock_httpx_response(200, {
            "choices": [{"message": {"content": "Hello from Ollama"}}]
        })
        with patch("httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.post = AsyncMock(return_value=mock_resp)
            mock_cls.return_value = mock_client

            result = await adapter.chat(
                model="llama3.2",
                messages=[{"role": "user", "content": "hello"}],
                timeout=30.0,
            )
        assert result.content == "Hello from Ollama"


# ===========================================================================
# AnthropicAdapter
# ===========================================================================

class TestAnthropicAdapter:
    """Anthropic adapter uses the Messages API with different wire format."""

    def test_default_url_is_anthropic(self):
        assert "anthropic.com" in AnthropicAdapter.DEFAULT_API_URL

    def test_constructor_sets_key_and_url(self):
        adapter = AnthropicAdapter(api_key="sk-ant-test")
        assert adapter.api_key == "sk-ant-test"
        assert "anthropic.com" in adapter.api_url

    def test_not_subclass_of_openrouter(self):
        assert not issubclass(AnthropicAdapter, OpenRouterAdapter)

    def test_requires_api_key(self):
        # Anthropic adapter allows None at construction but raises at chat.
        adapter = AnthropicAdapter(api_key=None)
        assert adapter is not None  # construction is permissive

    @pytest.mark.asyncio
    async def test_chat_success_text_block(self):
        adapter = AnthropicAdapter(api_key="sk-ant-test")
        mock_resp = _mock_httpx_response(200, ANTHROPIC_CHAT_RESPONSE)
        with patch("httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.post = AsyncMock(return_value=mock_resp)
            mock_cls.return_value = mock_client

            result = await adapter.chat(
                model="claude-sonnet-4-5",
                messages=[{"role": "user", "content": "hi"}],
                timeout=30.0,
            )
        assert isinstance(result, ProviderResponse)
        assert result.content == "Hello from Anthropic"

    @pytest.mark.asyncio
    async def test_chat_separates_system_messages(self):
        """System messages are sent in the top-level 'system' field."""
        adapter = AnthropicAdapter(api_key="sk-ant-test")
        mock_resp = _mock_httpx_response(200, ANTHROPIC_CHAT_RESPONSE)
        captured_body: list[dict] = []

        async def fake_post(url, *, headers, json, timeout=None):
            captured_body.append(json)
            return mock_resp

        with patch("httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.post = AsyncMock(side_effect=fake_post)
            mock_cls.return_value = mock_client

            await adapter.chat(
                model="claude-sonnet-4-5",
                messages=[
                    {"role": "system", "content": "Be helpful"},
                    {"role": "user", "content": "hi"},
                ],
                timeout=30.0,
            )

        assert captured_body, "No POST was made"
        body = captured_body[0]
        # System message must be at top level
        assert body.get("system") == "Be helpful"
        # Non-system messages go in 'messages'
        user_messages = body.get("messages", [])
        assert all(m["role"] != "system" for m in user_messages)

    @pytest.mark.asyncio
    async def test_chat_uses_correct_headers(self):
        adapter = AnthropicAdapter(api_key="sk-ant-my-key")
        mock_resp = _mock_httpx_response(200, ANTHROPIC_CHAT_RESPONSE)
        captured_headers: list[dict] = []

        async def fake_post(url, *, headers, json, timeout=None):
            captured_headers.append(headers)
            return mock_resp

        with patch("httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.post = AsyncMock(side_effect=fake_post)
            mock_cls.return_value = mock_client

            await adapter.chat(
                model="claude-opus-4-5",
                messages=[{"role": "user", "content": "hi"}],
                timeout=30.0,
            )

        assert captured_headers, "No POST was made"
        h = captured_headers[0]
        assert h.get("x-api-key") == "sk-ant-my-key"
        assert "anthropic-version" in h

    @pytest.mark.asyncio
    async def test_chat_auth_error_401(self):
        adapter = AnthropicAdapter(api_key="bad-key")
        mock_resp = _mock_httpx_response(401, {
            "error": {"type": "authentication_error", "message": "invalid key"}
        })
        with patch("httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.post = AsyncMock(return_value=mock_resp)
            mock_cls.return_value = mock_client

            with pytest.raises(ProviderAuthError):
                await adapter.chat(
                    model="claude-sonnet-4-5",
                    messages=[{"role": "user", "content": "hi"}],
                    timeout=30.0,
                )

    @pytest.mark.asyncio
    async def test_chat_rate_limit_429(self):
        adapter = AnthropicAdapter(api_key="sk-ant-test", max_retries=0)
        mock_resp = _mock_httpx_response(429, {
            "error": {"type": "rate_limit_error", "message": "slow down"}
        })
        with patch("httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.post = AsyncMock(return_value=mock_resp)
            mock_cls.return_value = mock_client

            with pytest.raises(ProviderRateLimitError):
                await adapter.chat(
                    model="claude-sonnet-4-5",
                    messages=[{"role": "user", "content": "hi"}],
                    timeout=30.0,
                )

    @pytest.mark.asyncio
    async def test_chat_timeout(self):
        adapter = AnthropicAdapter(api_key="sk-ant-test", max_retries=0)
        with patch("httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
            mock_cls.return_value = mock_client

            with pytest.raises(ProviderTimeoutError):
                await adapter.chat(
                    model="claude-sonnet-4-5",
                    messages=[{"role": "user", "content": "hi"}],
                    timeout=30.0,
                )

    @pytest.mark.asyncio
    async def test_chat_multiple_content_blocks_joined(self):
        """Multiple text content blocks are concatenated."""
        adapter = AnthropicAdapter(api_key="sk-ant-test")
        mock_resp = _mock_httpx_response(200, {
            "content": [
                {"type": "text", "text": "Part A"},
                {"type": "text", "text": " Part B"},
            ]
        })
        with patch("httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.post = AsyncMock(return_value=mock_resp)
            mock_cls.return_value = mock_client

            result = await adapter.chat(
                model="claude-sonnet-4-5",
                messages=[{"role": "user", "content": "hi"}],
                timeout=30.0,
            )
        assert "Part A" in result.content
        assert "Part B" in result.content
