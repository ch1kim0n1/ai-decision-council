"""FastAPI router factory with all council API endpoints."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from ai_decision_council.client import Council
from ai_decision_council.council import (
    calculate_aggregate_rankings,
    generate_conversation_title,
    stage1_collect_responses,
    stage2_collect_rankings,
    stage3_synthesize_final,
)

from .backends import StorageBackend
from .helpers import (
    _acquire_request_budget,
    _assert_conversation_owner,
    _current_owner_id,
    _make_envelope,
    _normalize_content,
    _public_conversation,
    _sse_event,
)
from .rate_limiter import InMemoryRateLimiter
from .request_models import SendMessageRequest
from .settings import APISettings

logger = logging.getLogger(__name__)


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


