"""Pluggable auth/storage backends for the FastAPI integration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Protocol
from uuid import UUID, uuid4

from fastapi import HTTPException, Request


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
        path = self.get_conversation_path(conversation_id)
        if not path.exists():
            return None
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def save_conversation(self, conversation: dict[str, Any]) -> None:
        normalized_id = _normalize_conversation_id(conversation["id"])
        payload = dict(conversation)
        payload["id"] = normalized_id
        path = self.get_conversation_path(normalized_id)
        with path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)

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
        conversation = self.get_conversation(conversation_id)
        if conversation is None:
            raise ValueError(f"Conversation {conversation_id} not found")

        message = {
            "id": str(uuid4()),
            "role": "user",
            "content": content,
            "created_at": _utc_now_iso(),
        }
        conversation["messages"].append(message)
        self.save_conversation(conversation)
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
        conversation = self.get_conversation(conversation_id)
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
        self.save_conversation(conversation)
        return message

    def update_conversation_title(self, conversation_id: str | UUID, title: str) -> None:
        conversation = self.get_conversation(conversation_id)
        if conversation is None:
            raise ValueError(f"Conversation {conversation_id} not found")
        conversation["title"] = title
        self.save_conversation(conversation)


class StaticTokenAuthBackend:
    """Bearer-token auth backend suitable for local and small deployments."""

    def __init__(self, tokens: set[str]):
        self._tokens = tokens

    @classmethod
    def from_env(cls) -> "StaticTokenAuthBackend":
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
        if token is None or token not in self._tokens:
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
        normalized = token.strip()
        return normalized or None

    @staticmethod
    def _owner_id_from_token(token: str) -> str:
        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        return digest[:32]

    @staticmethod
    def _fingerprint(token: str) -> str:
        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        return digest[:12]
