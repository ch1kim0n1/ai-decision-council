"""Pluggable auth/storage backends for the FastAPI integration."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import tempfile
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol, cast
from uuid import UUID, uuid4

from fastapi import HTTPException, Request

if os.name == "nt":
    import msvcrt
else:
    import fcntl


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_conversation_id(conversation_id: str | UUID) -> str:
    try:
        return str(UUID(str(conversation_id)))
    except ValueError as exc:
        raise ValueError("conversation_id must be a valid UUID") from exc


@dataclass(frozen=True)
class AuthContext:
    """Authenticated request context injected by auth backend."""

    owner_id: str
    token_fingerprint: str


class StorageBackend(Protocol):
    """Storage extension point for conversation persistence."""

    def create_conversation(
        self,
        conversation_id: str | UUID,
        owner_id: str | None = None,
    ) -> dict[str, Any]:
        ...

    def get_conversation(self, conversation_id: str | UUID) -> dict[str, Any] | None:
        ...

    def list_conversations(self, owner_id: str | None = None) -> list[dict[str, Any]]:
        ...

    def add_user_message(self, conversation_id: str | UUID, content: str) -> dict[str, Any]:
        ...

    def add_assistant_message(
        self,
        conversation_id: str | UUID,
        stage1: list[dict[str, Any]],
        stage2: list[dict[str, Any]],
        stage3: dict[str, Any],
        metadata: dict[str, Any] | None = None,
        errors: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        ...

    def update_conversation_title(self, conversation_id: str | UUID, title: str) -> None:
        ...


class AuthBackend(Protocol):
    """Auth extension point that validates the incoming request."""

    async def authenticate(self, request: Request) -> AuthContext:
        ...


class FileStorageBackend:
    """File-backed storage implementation for local and reference deployments."""

    _thread_lock_guard = threading.Lock()
    _thread_locks: dict[Path, threading.RLock] = {}

    def __init__(self, data_dir: str):
        self.data_dir = data_dir

    def ensure_data_dir(self) -> Path:
        path = Path(self.data_dir).resolve()
        path.mkdir(parents=True, exist_ok=True)
        return path

    def get_conversation_path(self, conversation_id: str | UUID) -> Path:
        base_dir = self.ensure_data_dir()
        normalized_id = _normalize_conversation_id(conversation_id)
        path = (base_dir / f"{normalized_id}.json").resolve()
        if path.parent != base_dir:
            raise ValueError("conversation_id resolves outside data directory")
        return path

    @classmethod
    def _thread_lock_for(cls, lock_path: Path) -> threading.RLock:
        with cls._thread_lock_guard:
            return cls._thread_locks.setdefault(lock_path, threading.RLock())

    @staticmethod
    def _lock_file(handle: Any) -> None:
        if os.name == "nt":
            handle.seek(0)
            if handle.read(1) == b"":
                handle.write(b"\0")
                handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        else:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)

    @staticmethod
    def _unlock_file(handle: Any) -> None:
        if os.name == "nt":
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    @contextmanager
    def _conversation_lock(self, normalized_id: str) -> Iterator[None]:
        base_dir = self.ensure_data_dir()
        lock_path = (base_dir / f"{normalized_id}.lock").resolve()
        if lock_path.parent != base_dir:
            raise ValueError("conversation_id lock resolves outside data directory")

        thread_lock = self._thread_lock_for(lock_path)
        with thread_lock, lock_path.open("a+b") as handle:
            self._lock_file(handle)
            try:
                yield
            finally:
                self._unlock_file(handle)

    def _read_conversation_unlocked(self, normalized_id: str) -> dict[str, Any] | None:
        path = self.get_conversation_path(normalized_id)
        if not path.exists():
            return None
        with path.open("r", encoding="utf-8") as handle:
            return cast(dict[str, Any], json.load(handle))

    def _write_conversation_unlocked(
        self,
        normalized_id: str,
        conversation: dict[str, Any],
    ) -> None:
        payload = dict(conversation)
        payload["id"] = normalized_id
        path = self.get_conversation_path(normalized_id)
        fd, tmp_name = tempfile.mkstemp(
            prefix=f".{normalized_id}.",
            suffix=".tmp",
            dir=path.parent,
        )
        tmp_path = Path(tmp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as tmp:
                json.dump(payload, tmp, indent=2)
                tmp.write("\n")
                tmp.flush()
                os.fsync(tmp.fileno())
            os.replace(tmp_path, path)
        except Exception:
            tmp_path.unlink(missing_ok=True)
            raise

    def create_conversation(
        self,
        conversation_id: str | UUID,
        owner_id: str | None = None,
    ) -> dict[str, Any]:
        normalized_id = _normalize_conversation_id(conversation_id)
        conversation: dict[str, Any] = {
            "id": normalized_id,
            "owner_id": owner_id,
            "created_at": _utc_now_iso(),
            "title": "New Conversation",
            "messages": [],
        }
        self.save_conversation(conversation)
        return conversation

    def get_conversation(self, conversation_id: str | UUID) -> dict[str, Any] | None:
        normalized_id = _normalize_conversation_id(conversation_id)
        with self._conversation_lock(normalized_id):
            return self._read_conversation_unlocked(normalized_id)

    def save_conversation(self, conversation: dict[str, Any]) -> None:
        normalized_id = _normalize_conversation_id(conversation["id"])
        with self._conversation_lock(normalized_id):
            self._write_conversation_unlocked(normalized_id, conversation)

    def list_conversations(self, owner_id: str | None = None) -> list[dict[str, Any]]:
        base_dir = self.ensure_data_dir()
        conversations: list[dict[str, Any]] = []

        for path in sorted(base_dir.glob("*.json")):
            try:
                with path.open("r", encoding="utf-8") as handle:
                    data = json.load(handle)
            except (json.JSONDecodeError, OSError):
                continue

            if owner_id is not None and data.get("owner_id") != owner_id:
                continue

            messages = data.get("messages", [])
            conversations.append(
                {
                    "id": str(data.get("id", path.stem)),
                    "created_at": str(data.get("created_at", "")),
                    "title": str(data.get("title", "New Conversation")),
                    "message_count": len(messages) if isinstance(messages, list) else 0,
                }
            )

        conversations.sort(key=lambda item: item["created_at"], reverse=True)
        return conversations

    def add_user_message(self, conversation_id: str | UUID, content: str) -> dict[str, Any]:
        normalized_id = _normalize_conversation_id(conversation_id)
        with self._conversation_lock(normalized_id):
            conversation = self._read_conversation_unlocked(normalized_id)
            if conversation is None:
                raise ValueError(f"Conversation {conversation_id} not found")

            message = {
                "id": str(uuid4()),
                "role": "user",
                "content": content,
                "created_at": _utc_now_iso(),
            }
            conversation["messages"].append(message)
            self._write_conversation_unlocked(normalized_id, conversation)
            return message

    def add_assistant_message(
        self,
        conversation_id: str | UUID,
        stage1: list[dict[str, Any]],
        stage2: list[dict[str, Any]],
        stage3: dict[str, Any],
        metadata: dict[str, Any] | None = None,
        errors: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        normalized_id = _normalize_conversation_id(conversation_id)
        with self._conversation_lock(normalized_id):
            conversation = self._read_conversation_unlocked(normalized_id)
            if conversation is None:
                raise ValueError(f"Conversation {conversation_id} not found")

            message = {
                "id": str(uuid4()),
                "role": "assistant",
                "stage1": stage1,
                "stage2": stage2,
                "stage3": stage3,
                "metadata": metadata or {},
                "errors": errors or [],
                "created_at": _utc_now_iso(),
            }
            conversation["messages"].append(message)
            self._write_conversation_unlocked(normalized_id, conversation)
            return message

    def update_conversation_title(self, conversation_id: str | UUID, title: str) -> None:
        normalized_id = _normalize_conversation_id(conversation_id)
        with self._conversation_lock(normalized_id):
            conversation = self._read_conversation_unlocked(normalized_id)
            if conversation is None:
                raise ValueError(f"Conversation {conversation_id} not found")
            conversation["title"] = title
            self._write_conversation_unlocked(normalized_id, conversation)


class StaticTokenAuthBackend:
    """Bearer-token auth backend suitable for local and small deployments."""

    def __init__(self, tokens: set[str]):
        self._tokens = tokens
        # Pre-compute fixed-length SHA256 digests so comparison is both
        # constant-time and independent of token length.
        self._token_digests = [self._digest(token) for token in tokens]

    @staticmethod
    def _digest(token: str) -> bytes:
        return hashlib.sha256(token.encode()).digest()

    def _is_valid(self, token: str) -> bool:
        """Constant-time membership check against configured tokens.

        Compares fixed-length SHA256 digests with ``hmac.compare_digest`` to
        avoid both data-dependent early exit and token-length leakage.  All
        configured digests are checked (no short-circuit on first match) so the
        timing does not reveal which token matched.
        """
        candidate = self._digest(token)
        matched = False
        for digest in self._token_digests:
            if hmac.compare_digest(candidate, digest):
                matched = True
        return matched

    @classmethod
    def from_env(cls) -> StaticTokenAuthBackend:
        raw = os.getenv("LLM_COUNCIL_REFERENCE_API_KEYS") or os.getenv(
            "LLM_COUNCIL_REFERENCE_API_TOKEN"
        )
        if not raw:
            return cls(tokens=set())
        tokens = {part.strip() for part in raw.split(",") if part.strip()}
        return cls(tokens=tokens)

    async def authenticate(self, request: Request) -> AuthContext:
        if not self._tokens:
            raise HTTPException(
                status_code=503,
                detail="Reference API auth is not configured.",
            )

        token = self._parse_authorization_token(request.headers.get("authorization"))
        if token is None or not self._is_valid(token):
            raise HTTPException(status_code=401, detail="Unauthorized.")

        owner_id = self._owner_id_from_token(token)
        return AuthContext(
            owner_id=owner_id,
            token_fingerprint=self._fingerprint(token),
        )

    @staticmethod
    def _parse_authorization_token(auth_header: str | None) -> str | None:
        if not auth_header:
            return None
        scheme, _, token = auth_header.partition(" ")
        if scheme.lower() != "bearer":
            return None
        return token.strip() or None

    @staticmethod
    def _fingerprint(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()[:16]

    @staticmethod
    def _owner_id_from_token(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()[:12]
