"""Generated type definitions for ai-decision-council API."""

from __future__ import annotations

from typing import Any, TypedDict


class ApiError(TypedDict):
    code: str
    message: str


class ApiEnvelope(TypedDict):
    data: Any | None
    metadata: dict[str, Any]
    errors: list[ApiError]


class ConversationSummary(TypedDict):
    id: str
    created_at: str
    title: str
    message_count: int


class Conversation(TypedDict):
    id: str
    created_at: str
    title: str
    messages: list[dict[str, Any]]


class AssistantMessage(TypedDict, total=False):
    id: str
    role: str
    stage1: list[dict[str, Any]]
    stage2: list[dict[str, Any]]
    stage3: dict[str, Any]
    metadata: dict[str, Any]
    errors: list[ApiError]
    created_at: str


class SendMessageData(TypedDict, total=False):
    conversation: Conversation
    assistant_message: AssistantMessage
    result: dict[str, Any]


class StreamEvent(TypedDict):
    event_type: str
    event_id: str | None
    envelope: ApiEnvelope
