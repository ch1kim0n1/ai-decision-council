"""Internal helper functions for the FastAPI integration."""

from __future__ import annotations

import json
from typing import Any

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

from .backends import AuthContext
from .rate_limiter import InMemoryRateLimiter
from .settings import APISettings, _now_iso


def _make_envelope(
    request: Request,
    data: Any,
    metadata: dict[str, Any] | None = None,
    errors: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    response_metadata = {"request_id": request.state.request_id, "timestamp": _now_iso()}
    if metadata:
        response_metadata.update(metadata)
    return {"data": data, "metadata": response_metadata, "errors": errors or []}


def _error_response(
    request: Request,
    *,
    status_code: int,
    code: str,
    message: str,
) -> JSONResponse:
    response = JSONResponse(
        status_code=status_code,
        content=_make_envelope(
            request,
            data=None,
            errors=[{"code": code, "message": message}],
        ),
    )
    response.headers["X-Request-ID"] = request.state.request_id
    return response


def _sse_event(
    request: Request,
    event_id: int,
    event_name: str,
    data: Any,
    metadata: dict[str, Any] | None = None,
    errors: list[dict[str, Any]] | None = None,
) -> str:
    event_metadata = {"event": event_name, "event_id": event_id}
    if metadata:
        event_metadata.update(metadata)
    payload = _make_envelope(request, data=data, metadata=event_metadata, errors=errors)
    return f"id: {event_id}\nevent: {event_name}\ndata: {json.dumps(payload)}\n\n"


def _public_conversation(conversation: dict[str, Any]) -> dict[str, Any]:
    payload = dict(conversation)
    payload.pop("owner_id", None)
    return payload


def _assert_conversation_owner(conversation: dict[str, Any], owner_id: str) -> None:
    if conversation.get("owner_id") != owner_id:
        raise HTTPException(status_code=404, detail="Conversation not found")


def _normalize_content(content: str, *, max_chars: int) -> str:
    normalized = content.strip()
    if not normalized:
        raise HTTPException(status_code=422, detail="content must not be empty")
    if len(normalized) > max_chars:
        raise HTTPException(
            status_code=422,
            detail=f"content must be <= {max_chars} characters",
        )
    return normalized


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def _current_owner_id(request: Request) -> str:
    auth_context = getattr(request.state, "auth_context", None)
    if not isinstance(auth_context, AuthContext):
        raise HTTPException(status_code=401, detail="Unauthorized.")
    return auth_context.owner_id


async def _acquire_request_budget(
    request: Request,
    *,
    settings: APISettings,
    limiter: InMemoryRateLimiter,
) -> list[str]:
    owner_key = f"owner:{_current_owner_id(request)}"
    ip_key = f"ip:{_client_ip(request)}"
    keys = [owner_key, ip_key]

    allowed, reason = await limiter.acquire(
        keys,
        window_seconds=settings.rate_limit_window_seconds,
        max_requests=settings.rate_limit_max_requests,
        max_concurrent=settings.rate_limit_max_concurrent,
    )
    if not allowed:
        if reason == "concurrency_exceeded":
            raise HTTPException(
                status_code=429,
                detail="Too many concurrent requests. Please retry shortly.",
            )
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Please retry later.")
    return keys


