"""End-to-end tests for the FastAPI integration: auth, owner isolation, rate limiting.

Covers issue #24 (FastAPI app/router/auth had zero test coverage).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from ai_decision_council.api.fastapi.app import create_app
from ai_decision_council.api.fastapi.backends import StaticTokenAuthBackend
from ai_decision_council.api.fastapi.settings import APISettings
from ai_decision_council.schemas import CouncilResult

TOKEN_A = "token-aaa"
TOKEN_B = "token-bbb"


def _auth_a() -> dict[str, str]:
    return {"Authorization": f"Bearer {TOKEN_A}"}


def _auth_b() -> dict[str, str]:
    return {"Authorization": f"Bearer {TOKEN_B}"}


def _fake_council_factory() -> Any:
    """Return a council whose run() yields a fixed CouncilResult (no network)."""
    council = MagicMock()
    council.config = MagicMock()
    council.provider_adapter = MagicMock()
    council.metadata = MagicMock(return_value={"provider": "test"})
    council.run = AsyncMock(
        return_value=CouncilResult(
            stage1=[{"model": "m", "response": "hi"}],
            stage2=[],
            stage3={"model": "m", "response": "final"},
            metadata={"errors": []},
            errors=[],
        )
    )
    return council


def _make_client(
    tmp_path: Any,
    *,
    tokens: set[str] | None = None,
    settings: APISettings | None = None,
) -> TestClient:
    resolved_settings = settings or APISettings(data_dir=str(tmp_path / "conversations"))
    auth = StaticTokenAuthBackend(tokens={TOKEN_A, TOKEN_B} if tokens is None else tokens)
    app = create_app(
        settings=resolved_settings,
        auth_backend=auth,
        council_factory=_fake_council_factory,
    )
    return TestClient(app)


class TestAuth:
    def test_root_is_public(self, tmp_path: Any) -> None:
        client = _make_client(tmp_path)
        resp = client.get("/")
        assert resp.status_code == 200

    def test_valid_token_200(self, tmp_path: Any) -> None:
        client = _make_client(tmp_path)
        resp = client.get("/v1/conversations", headers=_auth_a())
        assert resp.status_code == 200
        assert resp.json()["data"]["conversations"] == []

    def test_missing_token_401(self, tmp_path: Any) -> None:
        client = _make_client(tmp_path)
        resp = client.get("/v1/conversations")
        assert resp.status_code == 401
        assert resp.headers.get("WWW-Authenticate") == "Bearer"

    def test_wrong_token_401(self, tmp_path: Any) -> None:
        client = _make_client(tmp_path)
        resp = client.get("/v1/conversations", headers={"Authorization": "Bearer nope"})
        assert resp.status_code == 401

    def test_unconfigured_auth_503(self, tmp_path: Any) -> None:
        client = _make_client(tmp_path, tokens=set())
        resp = client.get("/v1/conversations", headers=_auth_a())
        assert resp.status_code == 503


class TestOwnerIsolation:
    def test_owner_cannot_see_other_owner_conversation(self, tmp_path: Any) -> None:
        client = _make_client(tmp_path)
        created = client.post("/v1/conversations", headers=_auth_a())
        assert created.status_code == 200
        conv_id = created.json()["data"]["conversation"]["id"]

        # Owner A sees it.
        assert client.get(f"/v1/conversations/{conv_id}", headers=_auth_a()).status_code == 200
        # Owner B is denied (404, not leaking existence).
        assert client.get(f"/v1/conversations/{conv_id}", headers=_auth_b()).status_code == 404

    def test_list_scoped_to_owner(self, tmp_path: Any) -> None:
        client = _make_client(tmp_path)
        client.post("/v1/conversations", headers=_auth_a())
        a_list = client.get("/v1/conversations", headers=_auth_a()).json()
        b_list = client.get("/v1/conversations", headers=_auth_b()).json()
        assert len(a_list["data"]["conversations"]) == 1
        assert len(b_list["data"]["conversations"]) == 0


class TestRateLimiting:
    def test_message_rate_limit_exceeded(self, tmp_path: Any) -> None:
        settings = APISettings(
            data_dir=str(tmp_path / "conversations"),
            rate_limit_window_seconds=60,
            rate_limit_max_requests=1,
            rate_limit_max_concurrent=5,
        )
        client = _make_client(tmp_path, settings=settings)
        conv_id = client.post("/v1/conversations", headers=_auth_a()).json()[
            "data"
        ]["conversation"]["id"]

        first = client.post(
            f"/v1/conversations/{conv_id}/message",
            headers=_auth_a(),
            json={"content": "hello"},
        )
        assert first.status_code == 200

        second = client.post(
            f"/v1/conversations/{conv_id}/message",
            headers=_auth_a(),
            json={"content": "hello again"},
        )
        assert second.status_code == 429


class TestSendMessage:
    def test_send_message_returns_result(self, tmp_path: Any) -> None:
        client = _make_client(tmp_path)
        conv_id = client.post("/v1/conversations", headers=_auth_a()).json()[
            "data"
        ]["conversation"]["id"]
        resp = client.post(
            f"/v1/conversations/{conv_id}/message",
            headers=_auth_a(),
            json={"content": "what is 2+2?"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["result"]["stage3"]["response"] == "final"
