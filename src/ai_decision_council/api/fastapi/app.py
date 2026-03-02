"""FastAPI app factory and router for ai-decision-council."""

from __future__ import annotations

import asyncio
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import logging
import os
import time
from typing import Any, Callable
from uuid import UUID, uuid4

from ai_decision_council.client import Council
from ai_decision_council.council import (
    calculate_aggregate_rankings,
    generate_conversation_title,
    stage1_collect_responses,
    stage2_collect_rankings,
    stage3_synthesize_final,
)
from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from .backends import (
    AuthBackend,
    AuthContext,
    FileStorageBackend,
    StaticTokenAuthBackend,
    StorageBackend,
)


logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_list(name: str, default: list[str]) -> list[str]:
    raw = os.getenv(name)
    if raw is None:
        return default
    items = [part.strip() for part in raw.split(",") if part.strip()]
    return items or default


@dataclass(frozen=True)
class APISettings:
    """Runtime settings for the FastAPI integration."""

    api_prefix: str = "/v1"
    data_dir: str = "data/conversations"
    cors_origins: tuple[str, ...] = ("http://localhost:5173", "http://localhost:3000")
    rate_limit_window_seconds: int = 60
    rate_limit_max_requests: int = 8
    rate_limit_max_concurrent: int = 2
    max_content_chars: int = 20_000
    app_title: str = "LLM Council API"
    app_description: str = (
        "Versioned FastAPI integration for ai-decision-council. "
        "Use as a reusable module or standalone service."
    )

    @classmethod
    def from_env(cls) -> "APISettings":
        return cls(
            api_prefix=os.getenv("LLM_COUNCIL_API_PREFIX", "/v1"),
            data_dir=os.getenv("LLM_COUNCIL_DATA_DIR", "data/conversations"),
            cors_origins=tuple(
                _env_list(
                    "LLM_COUNCIL_CORS_ORIGINS",
                    ["http://localhost:5173", "http://localhost:3000"],
                )
            ),
            rate_limit_window_seconds=max(
                1, _env_int("LLM_COUNCIL_REFERENCE_RATE_LIMIT_WINDOW_SECONDS", 60)
            ),
            rate_limit_max_requests=max(
                1, _env_int("LLM_COUNCIL_REFERENCE_RATE_LIMIT_MAX_REQUESTS", 8)
            ),
            rate_limit_max_concurrent=max(
                1, _env_int("LLM_COUNCIL_REFERENCE_RATE_LIMIT_MAX_CONCURRENT", 2)
            ),
            max_content_chars=max(
                1, _env_int("LLM_COUNCIL_REFERENCE_MAX_CONTENT_CHARS", 20_000)
            ),
        )


class InMemoryRateLimiter:
    """Simple in-memory limiter for abuse protection."""

    def __init__(self):
        self._recent: dict[str, deque[float]] = defaultdict(deque)
        self._inflight: dict[str, int] = defaultdict(int)
        self._lock = asyncio.Lock()

    async def acquire(
        self,
        keys: list[str],
        *,
        window_seconds: int,
        max_requests: int,
        max_concurrent: int,
    ) -> tuple[bool, str | None]:
        now = time.monotonic()
        cutoff = now - window_seconds
        async with self._lock:
            for key in keys:
                recent = self._recent[key]
                while recent and recent[0] < cutoff:
                    recent.popleft()
                if len(recent) >= max_requests:
                    return False, "request_rate_exceeded"
                if self._inflight[key] >= max_concurrent:
                    return False, "concurrency_exceeded"

            for key in keys:
                self._recent[key].append(now)
                self._inflight[key] += 1
        return True, None

    async def release(self, keys: list[str]) -> None:
        async with self._lock:
            for key in keys:
                current = self._inflight.get(key, 0)
                if current <= 1:
                    self._inflight.pop(key, None)
                else:
                    self._inflight[key] = current - 1


class SendMessageRequest(BaseModel):
    """Request to send a user message through the council pipeline."""

    content: str = Field(min_length=1)


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


def create_router(
    *,
    settings: APISettings,
    storage_backend: StorageBackend,
    rate_limiter: InMemoryRateLimiter,
    council_factory: Callable[[], Council],
) -> APIRouter:
    """Create a mountable API router for embedded frameworks."""

    router = APIRouter()

    @router.get("/conversations")
    async def list_conversations(request: Request):
        conversations = storage_backend.list_conversations(owner_id=_current_owner_id(request))
        return _make_envelope(
            request,
            data={"conversations": conversations},
            metadata={"count": len(conversations)},
        )

    @router.post("/conversations")
    async def create_conversation(request: Request):
        conversation = storage_backend.create_conversation(
            str(uuid4()),
            owner_id=_current_owner_id(request),
        )
        return _make_envelope(request, data={"conversation": _public_conversation(conversation)})

    @router.get("/conversations/{conversation_id}")
    async def get_conversation(conversation_id: UUID, request: Request):
        conversation = storage_backend.get_conversation(conversation_id)
        if conversation is None:
            raise HTTPException(status_code=404, detail="Conversation not found")
        _assert_conversation_owner(conversation, _current_owner_id(request))
        return _make_envelope(
            request,
            data={"conversation": _public_conversation(conversation)},
        )

    @router.post("/conversations/{conversation_id}/message")
    async def send_message(conversation_id: UUID, request: Request, payload: SendMessageRequest):
        conversation = storage_backend.get_conversation(conversation_id)
        if conversation is None:
            raise HTTPException(status_code=404, detail="Conversation not found")
        owner_id = _current_owner_id(request)
        _assert_conversation_owner(conversation, owner_id)

        rate_limit_keys = await _acquire_request_budget(
            request,
            settings=settings,
            limiter=rate_limiter,
        )
        try:
            content = _normalize_content(payload.content, max_chars=settings.max_content_chars)
            is_first_message = len(conversation["messages"]) == 0
            storage_backend.add_user_message(conversation_id, content)

            council = council_factory()
            title_task = None
            if is_first_message:
                title_task = asyncio.create_task(
                    generate_conversation_title(
                        content,
                        config=council.config,
                        adapter=council.provider_adapter,
                    )
                )

            result = await council.run(content)

            if title_task:
                title = await title_task
                storage_backend.update_conversation_title(conversation_id, title)

            assistant_message = storage_backend.add_assistant_message(
                conversation_id=conversation_id,
                stage1=result.stage1,
                stage2=result.stage2,
                stage3=result.stage3,
                metadata=result.metadata,
                errors=[error.to_dict() for error in result.errors],
            )

            updated_conversation = storage_backend.get_conversation(conversation_id)
            if updated_conversation is None:
                raise HTTPException(
                    status_code=500,
                    detail="Conversation disappeared after update",
                )

            return _make_envelope(
                request,
                data={
                    "conversation": _public_conversation(updated_conversation),
                    "assistant_message": assistant_message,
                    "result": result.to_dict(),
                },
                metadata={
                    "conversation_id": str(conversation_id),
                    "runtime": council.metadata(),
                    "error_count": len(result.errors),
                },
            )
        finally:
            await rate_limiter.release(rate_limit_keys)

    @router.post("/conversations/{conversation_id}/message/stream")
    async def send_message_stream(
        conversation_id: UUID,
        request: Request,
        payload: SendMessageRequest,
    ):
        conversation = storage_backend.get_conversation(conversation_id)
        if conversation is None:
            raise HTTPException(status_code=404, detail="Conversation not found")
        owner_id = _current_owner_id(request)
        _assert_conversation_owner(conversation, owner_id)

        rate_limit_keys = await _acquire_request_budget(
            request,
            settings=settings,
            limiter=rate_limiter,
        )
        content = _normalize_content(payload.content, max_chars=settings.max_content_chars)
        is_first_message = len(conversation["messages"]) == 0
        storage_backend.add_user_message(conversation_id, content)
        council = council_factory()

        async def event_generator():
            event_id = 0
            stage1_results: list[dict[str, Any]] = []
            stage2_results: list[dict[str, Any]] = []
            stage3_result: dict[str, Any] = {
                "model": "error",
                "response": "Stream terminated before final synthesis.",
            }
            stage_metadata: dict[str, Any] = {}

            try:
                title_task = None
                if is_first_message:
                    title_task = asyncio.create_task(
                        generate_conversation_title(
                            content,
                            config=council.config,
                            adapter=council.provider_adapter,
                        )
                    )

                event_id += 1
                yield _sse_event(
                    request,
                    event_id,
                    "stage1_start",
                    {"status": "started", "stage": "stage1"},
                    metadata={"conversation_id": str(conversation_id)},
                )

                stage1_results = await stage1_collect_responses(
                    content,
                    config=council.config,
                    adapter=council.provider_adapter,
                )

                event_id += 1
                yield _sse_event(
                    request,
                    event_id,
                    "stage1_complete",
                    {"stage1": stage1_results},
                    metadata={"conversation_id": str(conversation_id)},
                )

                event_id += 1
                yield _sse_event(
                    request,
                    event_id,
                    "stage2_start",
                    {"status": "started", "stage": "stage2"},
                    metadata={"conversation_id": str(conversation_id)},
                )

                stage2_results, label_to_model = await stage2_collect_rankings(
                    content,
                    stage1_results,
                    config=council.config,
                    adapter=council.provider_adapter,
                )
                aggregate_rankings = calculate_aggregate_rankings(stage2_results, label_to_model)
                stage_metadata = {
                    "label_to_model": label_to_model,
                    "aggregate_rankings": aggregate_rankings,
                }

                event_id += 1
                yield _sse_event(
                    request,
                    event_id,
                    "stage2_complete",
                    {"stage2": stage2_results, "stage_metadata": stage_metadata},
                    metadata={"conversation_id": str(conversation_id)},
                )

                event_id += 1
                yield _sse_event(
                    request,
                    event_id,
                    "stage3_start",
                    {"status": "started", "stage": "stage3"},
                    metadata={"conversation_id": str(conversation_id)},
                )

                stage3_result = await stage3_synthesize_final(
                    content,
                    stage1_results,
                    stage2_results,
                    config=council.config,
                    adapter=council.provider_adapter,
                )

                event_id += 1
                yield _sse_event(
                    request,
                    event_id,
                    "stage3_complete",
                    {"stage3": stage3_result},
                    metadata={"conversation_id": str(conversation_id)},
                )

                if title_task:
                    title = await title_task
                    storage_backend.update_conversation_title(conversation_id, title)
                    event_id += 1
                    yield _sse_event(
                        request,
                        event_id,
                        "title_complete",
                        {"title": title},
                        metadata={"conversation_id": str(conversation_id)},
                    )

                assistant_message = storage_backend.add_assistant_message(
                    conversation_id=conversation_id,
                    stage1=stage1_results,
                    stage2=stage2_results,
                    stage3=stage3_result,
                    metadata=stage_metadata,
                )
                event_id += 1
                yield _sse_event(
                    request,
                    event_id,
                    "complete",
                    {"assistant_message": assistant_message},
                    metadata={"conversation_id": str(conversation_id)},
                )

            except Exception:
                logger.exception(
                    "Streaming pipeline failure request_id=%s conversation_id=%s",
                    request.state.request_id,
                    conversation_id,
                )
                error = {
                    "code": "stream_internal_error",
                    "message": "Streaming pipeline failed.",
                }
                storage_backend.add_assistant_message(
                    conversation_id=conversation_id,
                    stage1=stage1_results,
                    stage2=stage2_results,
                    stage3=stage3_result,
                    metadata=stage_metadata,
                    errors=[error],
                )
                event_id += 1
                yield _sse_event(
                    request,
                    event_id,
                    "error",
                    data=None,
                    metadata={"conversation_id": str(conversation_id)},
                    errors=[error],
                )
            finally:
                await rate_limiter.release(rate_limit_keys)

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    return router


def create_app(
    *,
    settings: APISettings | None = None,
    storage_backend: StorageBackend | None = None,
    auth_backend: AuthBackend | None = None,
    council_factory: Callable[[], Council] | None = None,
) -> FastAPI:
    """Create a reusable FastAPI app for hosted deployments."""

    resolved_settings = settings or APISettings.from_env()
    resolved_storage = storage_backend or FileStorageBackend(resolved_settings.data_dir)
    resolved_auth = auth_backend or StaticTokenAuthBackend.from_env()
    resolved_council_factory = council_factory or Council.from_env
    rate_limiter = InMemoryRateLimiter()

    app = FastAPI(
        title=resolved_settings.app_title,
        description=resolved_settings.app_description,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(resolved_settings.cors_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def request_context_middleware(request: Request, call_next):
        request_id = request.headers.get("x-request-id") or str(uuid4())
        request.state.request_id = request_id

        if request.url.path.startswith(resolved_settings.api_prefix):
            try:
                request.state.auth_context = await resolved_auth.authenticate(request)
            except HTTPException as exc:
                if exc.status_code == 401:
                    response = _error_response(
                        request,
                        status_code=401,
                        code="unauthorized",
                        message="Unauthorized.",
                    )
                    response.headers["WWW-Authenticate"] = "Bearer"
                    return response
                if exc.status_code == 503:
                    logger.error("FastAPI auth backend is not configured.")
                    return _error_response(
                        request,
                        status_code=503,
                        code="service_misconfigured",
                        message="Reference API auth is not configured.",
                    )
                return _error_response(
                    request,
                    status_code=exc.status_code,
                    code="auth_error",
                    message=str(exc.detail),
                )

        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    @app.exception_handler(HTTPException)
    async def http_error_handler(request: Request, exc: HTTPException) -> JSONResponse:
        message = str(exc.detail)
        if exc.status_code >= 500:
            message = "Internal server error."
        return _error_response(
            request,
            status_code=exc.status_code,
            code="http_error",
            message=message,
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, _exc: Exception) -> JSONResponse:
        logger.exception(
            "Unhandled request failure request_id=%s path=%s",
            getattr(request.state, "request_id", "unknown"),
            request.url.path,
        )
        return _error_response(
            request,
            status_code=500,
            code="internal_error",
            message="Internal server error.",
        )

    @app.get("/")
    async def root(request: Request):
        return _make_envelope(
            request,
            data={"status": "ok", "service": resolved_settings.app_title},
        )

    router = create_router(
        settings=resolved_settings,
        storage_backend=resolved_storage,
        rate_limiter=rate_limiter,
        council_factory=resolved_council_factory,
    )
    app.include_router(router, prefix=resolved_settings.api_prefix)
    return app
