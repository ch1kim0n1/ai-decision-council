"""Generated typed Python client for ai-decision-council API."""

from __future__ import annotations

from collections.abc import AsyncIterator
import json
from typing import Any, cast

import httpx

try:
    from .council_api_types import (
        ApiEnvelope,
        Conversation,
        ConversationSummary,
        SendMessageData,
        StreamEvent,
    )
except ImportError:  # pragma: no cover - generated fallback
    from council_api_types import (  # type: ignore
        ApiEnvelope,
        Conversation,
        ConversationSummary,
        SendMessageData,
        StreamEvent,
    )


def _parse_sse_block(block: str) -> tuple[str, str | None, str] | None:
    event_type = "message"
    event_id: str | None = None
    data_lines: list[str] = []

    for line in block.split("\n"):
        if not line or line.startswith(":"):
            continue
        if line.startswith("event:"):
            event_type = line[6:].strip() or "message"
            continue
        if line.startswith("id:"):
            event_id = line[3:].strip() or None
            continue
        if line.startswith("data:"):
            data_lines.append(line[5:].lstrip())

    if not data_lines:
        return None
    return event_type, event_id, "\n".join(data_lines)


class CouncilApiError(RuntimeError):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        request_id: str | None = None,
    ):
        self.status_code = status_code
        self.code = code
        self.request_id = request_id
        suffix = f" (request_id={request_id})" if request_id else ""
        super().__init__(f"{code}: {message}{suffix}")


class CouncilApiClient:
    def __init__(self, base_url: str, token: str, timeout: float = 60.0):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    @staticmethod
    def _extract_error(payload: ApiEnvelope) -> tuple[str, str, str | None]:
        errors = payload.get("errors", [])
        if isinstance(errors, list) and errors:
            first = errors[0] or {}
            code = str(first.get("code", "http_error"))
            message = str(first.get("message", "Request failed"))
        else:
            code = "http_error"
            message = "Request failed"

        metadata = payload.get("metadata", {})
        request_id = metadata.get("request_id") if isinstance(metadata, dict) else None
        return code, message, str(request_id) if request_id else None

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
    ) -> ApiEnvelope:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.request(
                method,
                f"{self.base_url}{path}",
                headers=self._headers(),
                json=json_body,
            )

        try:
            payload = cast(ApiEnvelope, response.json())
        except ValueError:
            payload = {"data": None, "metadata": {}, "errors": []}

        if not response.is_success:
            code, message, request_id = self._extract_error(payload)
            if request_id is None:
                request_id = response.headers.get("x-request-id")
            raise CouncilApiError(response.status_code, code, message, request_id)
        return payload

    async def list_conversations(self) -> list[ConversationSummary]:
        payload = await self._request("GET", f"/v1/conversations")
        data = payload.get("data") or {}
        if not isinstance(data, dict):
            return []
        conversations = data.get("conversations", [])
        if not isinstance(conversations, list):
            return []
        return cast(list[ConversationSummary], conversations)

    async def create_conversation(self) -> Conversation:
        payload = await self._request("POST", f"/v1/conversations")
        data = payload.get("data") or {}
        if not isinstance(data, dict):
            return cast(Conversation, {})
        conversation = data.get("conversation", {})
        return cast(Conversation, conversation if isinstance(conversation, dict) else {})

    async def get_conversation(self, conversation_id: str) -> Conversation:
        payload = await self._request("GET", f"/v1/conversations/{conversation_id}")
        data = payload.get("data") or {}
        if not isinstance(data, dict):
            return cast(Conversation, {})
        conversation = data.get("conversation", {})
        return cast(Conversation, conversation if isinstance(conversation, dict) else {})

    async def send_message(self, conversation_id: str, content: str) -> SendMessageData:
        payload = await self._request(
            "POST",
            f"/v1/conversations/{conversation_id}/message",
            json_body={"content": content},
        )
        data = payload.get("data") or {}
        return cast(SendMessageData, data if isinstance(data, dict) else {})

    async def send_message_stream(
        self,
        conversation_id: str,
        content: str,
    ) -> AsyncIterator[StreamEvent]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/v1/conversations/{conversation_id}/message/stream",
                headers=self._headers(),
                json={"content": content},
            ) as response:
                if not response.is_success:
                    body = await response.aread()
                    try:
                        payload = cast(ApiEnvelope, json.loads(body.decode("utf-8")))
                    except Exception:
                        payload = {"data": None, "metadata": {}, "errors": []}
                    code, message, request_id = self._extract_error(payload)
                    if request_id is None:
                        request_id = response.headers.get("x-request-id")
                    raise CouncilApiError(response.status_code, code, message, request_id)

                buffer = ""
                async for chunk in response.aiter_text():
                    buffer += chunk.replace("\r\n", "\n")
                    while "\n\n" in buffer:
                        block, buffer = buffer.split("\n\n", 1)
                        parsed = _parse_sse_block(block)
                        if parsed is None:
                            continue
                        event_type, event_id, data_text = parsed
                        try:
                            envelope = cast(ApiEnvelope, json.loads(data_text))
                        except json.JSONDecodeError:
                            continue
                        yield {
                            "event_type": event_type,
                            "event_id": event_id,
                            "envelope": envelope,
                        }
