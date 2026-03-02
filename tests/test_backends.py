"""Tests for FileStorageBackend, StaticTokenAuthBackend, and utility functions."""

from __future__ import annotations

import json
import os
import pytest
from pathlib import Path
from uuid import uuid4, UUID
from unittest.mock import MagicMock, AsyncMock, patch

from ai_decision_council.api.fastapi.backends import (
    FileStorageBackend,
    StaticTokenAuthBackend,
    AuthContext,
    _normalize_conversation_id,
    _utc_now_iso,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_storage(tmp_path: Path) -> FileStorageBackend:
    return FileStorageBackend(data_dir=str(tmp_path / "conversations"))


def _fresh_id() -> str:
    return str(uuid4())


# ---------------------------------------------------------------------------
# _normalize_conversation_id
# ---------------------------------------------------------------------------

class TestNormalizeConversationId:
    def test_valid_uuid_string(self):
        uid = str(uuid4())
        assert _normalize_conversation_id(uid) == uid

    def test_valid_uuid_object(self):
        uid = uuid4()
        assert _normalize_conversation_id(uid) == str(uid)

    def test_invalid_raises_value_error(self):
        with pytest.raises(ValueError):
            _normalize_conversation_id("not-a-uuid")

    def test_uppercase_normalized_to_lowercase(self):
        uid = str(uuid4()).upper()
        result = _normalize_conversation_id(uid)
        assert result == result.lower()


# ---------------------------------------------------------------------------
# _utc_now_iso
# ---------------------------------------------------------------------------

class TestUtcNowIso:
    def test_returns_string(self):
        assert isinstance(_utc_now_iso(), str)

    def test_contains_T_separator(self):
        assert "T" in _utc_now_iso()

    def test_contains_timezone_offset(self):
        result = _utc_now_iso()
        assert "+" in result or result.endswith("Z") or result.endswith("+00:00")


# ---------------------------------------------------------------------------
# FileStorageBackend - create & get
# ---------------------------------------------------------------------------

class TestFileStorageBackendCreate:
    def test_create_returns_conversation_dict(self, tmp_path):
        storage = _make_storage(tmp_path)
        uid = _fresh_id()
        conv = storage.create_conversation(uid, owner_id="user-1")
        assert conv["id"] == uid
        assert conv["owner_id"] == "user-1"
        assert conv["title"] == "New Conversation"
        assert conv["messages"] == []

    def test_create_writes_json_file(self, tmp_path):
        storage = _make_storage(tmp_path)
        uid = _fresh_id()
        storage.create_conversation(uid)
        path = storage.get_conversation_path(uid)
        assert path.exists()

    def test_create_persists_owner_id(self, tmp_path):
        storage = _make_storage(tmp_path)
        uid = _fresh_id()
        storage.create_conversation(uid, owner_id="owner-99")
        conv = storage.get_conversation(uid)
        assert conv is not None
        assert conv["owner_id"] == "owner-99"

    def test_get_non_existent_returns_none(self, tmp_path):
        storage = _make_storage(tmp_path)
        assert storage.get_conversation(_fresh_id()) is None


# ---------------------------------------------------------------------------
# FileStorageBackend - messages
# ---------------------------------------------------------------------------

class TestFileStorageBackendMessages:
    def test_add_user_message(self, tmp_path):
        storage = _make_storage(tmp_path)
        uid = _fresh_id()
        storage.create_conversation(uid)
        msg = storage.add_user_message(uid, "Hello!")
        assert msg["role"] == "user"
        assert msg["content"] == "Hello!"

    def test_add_user_message_persisted(self, tmp_path):
        storage = _make_storage(tmp_path)
        uid = _fresh_id()
        storage.create_conversation(uid)
        storage.add_user_message(uid, "Persisted?")
        conv = storage.get_conversation(uid)
        assert any(m["content"] == "Persisted?" for m in conv["messages"])  # type: ignore[index]

    def test_add_assistant_message(self, tmp_path):
        storage = _make_storage(tmp_path)
        uid = _fresh_id()
        storage.create_conversation(uid)
        msg = storage.add_assistant_message(
            uid,
            stage1=[{"model": "m1", "response": "r1"}],
            stage2=[],
            stage3={"model": "m1", "response": "final"},
            metadata={},
            errors=[],
        )
        assert msg["role"] == "assistant"

    def test_multiple_messages_ordered(self, tmp_path):
        storage = _make_storage(tmp_path)
        uid = _fresh_id()
        storage.create_conversation(uid)
        storage.add_user_message(uid, "First")
        storage.add_user_message(uid, "Second")
        conv = storage.get_conversation(uid)
        contents = [m["content"] for m in conv["messages"]]  # type: ignore[index]
        assert contents.index("First") < contents.index("Second")


# ---------------------------------------------------------------------------
# FileStorageBackend - list & title
# ---------------------------------------------------------------------------

class TestFileStorageBackendList:
    def test_list_all_conversations(self, tmp_path):
        storage = _make_storage(tmp_path)
        ids = [_fresh_id() for _ in range(3)]
        for uid in ids:
            storage.create_conversation(uid)
        listed = storage.list_conversations()
        listed_ids = {c["id"] for c in listed}
        for uid in ids:
            assert uid in listed_ids

    def test_list_filters_by_owner(self, tmp_path):
        storage = _make_storage(tmp_path)
        uid_a = _fresh_id()
        uid_b = _fresh_id()
        storage.create_conversation(uid_a, owner_id="alice")
        storage.create_conversation(uid_b, owner_id="bob")
        alice_convs = storage.list_conversations(owner_id="alice")
        assert all(c["id"] == uid_a for c in alice_convs)

    def test_list_empty_directory(self, tmp_path):
        storage = _make_storage(tmp_path)
        assert storage.list_conversations() == []

    def test_update_conversation_title(self, tmp_path):
        storage = _make_storage(tmp_path)
        uid = _fresh_id()
        storage.create_conversation(uid)
        storage.update_conversation_title(uid, "My New Title")
        conv = storage.get_conversation(uid)
        assert conv is not None
        assert conv["title"] == "My New Title"


# ---------------------------------------------------------------------------
# FileStorageBackend - path traversal protection
# ---------------------------------------------------------------------------

class TestFileStorageBackendSecurity:
    def test_invalid_uuid_raises(self, tmp_path):
        storage = _make_storage(tmp_path)
        with pytest.raises((ValueError, Exception)):
            storage.get_conversation_path("../../etc/passwd")


# ---------------------------------------------------------------------------
# StaticTokenAuthBackend
# ---------------------------------------------------------------------------

class TestStaticTokenAuthBackend:
    def _make_request(self, token: str | None) -> MagicMock:
        req = MagicMock()
        auth = f"Bearer {token}" if token is not None else None
        req.headers = {"authorization": auth} if auth else {}
        return req

    @pytest.mark.asyncio
    async def test_valid_token_returns_auth_context(self):
        backend = StaticTokenAuthBackend(tokens={"secret-token"})
        req = self._make_request("secret-token")
        ctx = await backend.authenticate(req)
        assert isinstance(ctx, AuthContext)
        assert ctx.owner_id is not None

    @pytest.mark.asyncio
    async def test_invalid_token_raises_http_exception(self):
        from fastapi import HTTPException
        backend = StaticTokenAuthBackend(tokens={"secret-token"})
        req = self._make_request("wrong-token")
        with pytest.raises(HTTPException) as exc_info:
            await backend.authenticate(req)
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_missing_token_raises_http_exception(self):
        from fastapi import HTTPException
        backend = StaticTokenAuthBackend(tokens={"secret-token"})
        req = self._make_request(None)
        with pytest.raises(HTTPException):
            await backend.authenticate(req)

    @pytest.mark.asyncio
    async def test_no_configured_tokens_raises_503(self):
        from fastapi import HTTPException
        backend = StaticTokenAuthBackend(tokens=set())
        req = self._make_request("any-token")
        with pytest.raises(HTTPException) as exc_info:
            await backend.authenticate(req)
        assert exc_info.value.status_code == 503

    def test_fingerprint_is_deterministic(self):
        fp1 = StaticTokenAuthBackend._fingerprint("abc")
        fp2 = StaticTokenAuthBackend._fingerprint("abc")
        assert fp1 == fp2

    def test_different_tokens_different_fingerprints(self):
        assert StaticTokenAuthBackend._fingerprint("abc") != StaticTokenAuthBackend._fingerprint("xyz")

    def test_from_env_reads_env_var(self):
        with patch.dict(os.environ, {"LLM_COUNCIL_REFERENCE_API_TOKEN": "tok1,tok2"}):
            backend = StaticTokenAuthBackend.from_env()
            assert "tok1" in backend._tokens
            assert "tok2" in backend._tokens

    def test_from_env_empty_returns_empty_set(self):
        env = {k: v for k, v in os.environ.items()
               if k not in ("LLM_COUNCIL_REFERENCE_API_TOKEN", "LLM_COUNCIL_REFERENCE_API_KEYS")}
        with patch.dict(os.environ, env, clear=True):
            backend = StaticTokenAuthBackend.from_env()
            assert backend._tokens == set()
