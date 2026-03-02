"""CLI entrypoints for ai-decision-council package."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
import secrets
import sys
from typing import Any, Sequence

from dotenv import load_dotenv

from .client import Council
from .config import CouncilConfig
from .models import DEFAULT_MODEL_CATALOG, MAX_MODELS, MIN_MODELS


ENV_TEMPLATE = """# AI Decision Council runtime configuration
# Core provider key:
LLM_COUNCIL_API_KEY=

# Legacy key name (optional fallback):
# OPENROUTER_API_KEY=

# FastAPI auth token (required when using API module):
LLM_COUNCIL_REFERENCE_API_TOKEN=
# Optional frontend token override:
# VITE_REFERENCE_API_TOKEN=

# Option A: Explicit model list (recommended for full control)
# LLM_COUNCIL_MODELS=openai/gpt-5.1,anthropic/claude-sonnet-4.5,google/gemini-3-pro-preview,x-ai/grok-4,deepseek/deepseek-r1

# Option B: Use curated defaults by count (2-20, default 5)
LLM_COUNCIL_MODEL_COUNT=5

# Optional model overrides:
LLM_COUNCIL_CHAIRMAN_MODEL=openai/gpt-5.1
LLM_COUNCIL_TITLE_MODEL=openai/gpt-5.1

# Provider config:
LLM_COUNCIL_PROVIDER=openrouter
LLM_COUNCIL_API_URL=https://openrouter.ai/api/v1/chat/completions

# API routing/cors:
LLM_COUNCIL_API_PREFIX=/v1
# LLM_COUNCIL_CORS_ORIGINS=http://localhost:5173,http://localhost:3000

# Reliability tuning:
LLM_COUNCIL_MAX_RETRIES=2
LLM_COUNCIL_RETRY_BACKOFF_SECONDS=0.5
LLM_COUNCIL_STAGE_TIMEOUT_SECONDS=120
LLM_COUNCIL_TITLE_TIMEOUT_SECONDS=30

# API abuse controls:
LLM_COUNCIL_REFERENCE_RATE_LIMIT_WINDOW_SECONDS=60
LLM_COUNCIL_REFERENCE_RATE_LIMIT_MAX_REQUESTS=8
LLM_COUNCIL_REFERENCE_RATE_LIMIT_MAX_CONCURRENT=2
"""


BRIDGE_TEMPLATE = '''"""Project-local bridge for ai-decision-council integration.

Quickstart:
1) Fill env vars (run `ai-decision-council init` if needed)
2) Verify setup with `ai-decision-council doctor`
3) Call `ask_council(...)` or `run_council(...)` from your app
"""

from ai_decision_council import Council


council = Council.from_env()


async def ask_council(prompt: str) -> str:
    """Return only the final synthesized response."""
    return await council.ask(prompt)


async def run_council(prompt: str) -> dict:
    """Return full structured council output."""
    result = await council.run(prompt)
    return result.to_dict()
'''


FASTAPI_STANDALONE_TEMPLATE = '''"""Standalone FastAPI app using ai-decision-council API module."""

from ai_decision_council.api.fastapi import create_app


app = create_app()
'''


FASTAPI_EMBED_TEMPLATE = '''"""Embedded FastAPI router example for existing applications."""

from fastapi import FastAPI
from ai_decision_council.api.fastapi import APISettings, create_router, FileStorageBackend, StaticTokenAuthBackend, InMemoryRateLimiter
from ai_decision_council import Council


app = FastAPI(title="My Existing App")
settings = APISettings.from_env()
router = create_router(
    settings=settings,
    storage_backend=FileStorageBackend(settings.data_dir),
    rate_limiter=InMemoryRateLimiter(),
    council_factory=Council.from_env,
)
app.include_router(router, prefix=settings.api_prefix)
'''


DOCKERFILE_TEMPLATE = """FROM python:3.11-slim

WORKDIR /app
COPY . /app

RUN pip install --no-cache-dir ai-decision-council[api]

EXPOSE 8001
CMD ["uvicorn", "ai_decision_council_fastapi_app:app", "--host", "0.0.0.0", "--port", "8001"]
"""


DOCKER_COMPOSE_TEMPLATE = """version: "3.9"
services:
  council-api:
    build: .
    ports:
      - "8001:8001"
    env_file:
      - .env
"""


def _write_file(path: Path, content: str, force: bool) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not force:
        print(f"File exists, use --force to overwrite: {path}", file=sys.stderr)
        return False
    path.write_text(content, encoding="utf-8")
    print(f"Created: {path}")
    return True


def _format_model_list(models: list[str]) -> str:
    return "\n".join([f"- {model}" for model in models])


def cmd_init(args: argparse.Namespace) -> int:
    target_dir = Path(args.path).resolve()
    env_path = target_dir / ".env.ai-decision-council.example"
    wrote: list[bool] = [_write_file(env_path, ENV_TEMPLATE, force=args.force)]

    if args.api in {"bridge", "all"}:
        bridge_path = target_dir / "ai_decision_council_bridge.py"
        wrote.append(_write_file(bridge_path, BRIDGE_TEMPLATE, force=args.force))

    if args.api in {"fastapi", "all"}:
        wrote.extend(
            [
                _write_file(
                    target_dir / "ai_decision_council_fastapi_app.py",
                    FASTAPI_STANDALONE_TEMPLATE,
                    force=args.force,
                ),
                _write_file(
                    target_dir / "ai_decision_council_fastapi_embedded.py",
                    FASTAPI_EMBED_TEMPLATE,
                    force=args.force,
                ),
                _write_file(
                    target_dir / "Dockerfile.ai-decision-council",
                    DOCKERFILE_TEMPLATE,
                    force=args.force,
                ),
                _write_file(
                    target_dir / "docker-compose.ai-decision-council.yml",
                    DOCKER_COMPOSE_TEMPLATE,
                    force=args.force,
                ),
            ]
        )

    return 0 if all(wrote) else 1


def cmd_bridge(args: argparse.Namespace) -> int:
    output_path = Path(args.output).resolve()
    success = _write_file(output_path, BRIDGE_TEMPLATE, force=args.force)
    return 0 if success else 1


def cmd_doctor(_args: argparse.Namespace) -> int:
    load_dotenv()

    try:
        config = CouncilConfig.from_env()
    except ValueError as exc:
        print(f"Configuration invalid: {exc}", file=sys.stderr)
        return 1

    print("AI Decision Council doctor report")
    print(f"- API key configured: {'yes' if bool(config.api_key) else 'no'}")
    print(f"- Provider: {config.provider}")
    print(f"- Models configured: {len(config.models or [])}")
    print(f"- Chairman model: {config.chairman_model or 'unset'}")
    print(f"- Title model: {config.title_model or 'unset'}")
    print(f"- API URL: {config.api_url}")
    print(f"- Retries: {config.max_retries}")

    if not config.api_key:
        print(
            "Missing LLM_COUNCIL_API_KEY (or OPENROUTER_API_KEY fallback).",
            file=sys.stderr,
        )
        return 1

    models = config.models or []
    if len(models) < MIN_MODELS or len(models) > MAX_MODELS:
        print(
            f"Model count must be between {MIN_MODELS} and {MAX_MODELS}.",
            file=sys.stderr,
        )
        return 1

    chairman = config.chairman_model or ""
    if chairman not in models:
        print(
            "chairman_model must be present in selected model list.",
            file=sys.stderr,
        )
        return 1

    return 0


def cmd_models(args: argparse.Namespace) -> int:
    if args.defaults:
        if args.count is not None:
            if args.count < MIN_MODELS or args.count > MAX_MODELS:
                print(
                    f"count must be between {MIN_MODELS} and {MAX_MODELS}",
                    file=sys.stderr,
                )
                return 1
            selected = DEFAULT_MODEL_CATALOG[: args.count]
            print(_format_model_list(selected))
            return 0

        print(_format_model_list(DEFAULT_MODEL_CATALOG))
        return 0

    try:
        config = CouncilConfig.from_env()
    except ValueError as exc:
        print(f"Configuration invalid: {exc}", file=sys.stderr)
        return 1

    print(_format_model_list(list(config.models or [])))
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    load_dotenv()

    try:
        council = Council.from_env()
    except ValueError as exc:
        print(f"Configuration invalid: {exc}", file=sys.stderr)
        return 1

    if not council.config.api_key:
        print(
            "Missing LLM_COUNCIL_API_KEY. Run `ai-decision-council doctor` for setup help.",
            file=sys.stderr,
        )
        return 1

    try:
        result = asyncio.run(council.run(args.prompt))
    except Exception as exc:  # pragma: no cover - runtime safety
        print(f"Council run failed: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print(result.final_response)
    return 0


def _import_fastapi_integration():
    try:
        from .api.fastapi import APISettings, create_app
    except Exception as exc:  # pragma: no cover - import guard
        print(
            "FastAPI integration unavailable. Install with `pip install ai-decision-council[api]`.",
            file=sys.stderr,
        )
        print(f"Import error: {exc}", file=sys.stderr)
        return None, None
    return APISettings, create_app


def cmd_api_serve(args: argparse.Namespace) -> int:
    load_dotenv()
    _settings_cls, create_app = _import_fastapi_integration()
    if create_app is None:
        return 1

    try:
        import uvicorn
    except Exception as exc:  # pragma: no cover - import guard
        print(f"Unable to import uvicorn: {exc}", file=sys.stderr)
        return 1

    app = create_app()
    uvicorn.run(app, host=args.host, port=args.port, reload=args.reload)
    return 0


def cmd_api_openapi(args: argparse.Namespace) -> int:
    load_dotenv()
    schema = _resolve_openapi_schema()
    if schema is None:
        return 1

    output_path = Path(args.output).resolve()
    success = _write_file(
        output_path,
        json.dumps(schema, indent=2) + "\n",
        force=args.force,
    )
    return 0 if success else 1


def _detect_api_prefix(schema: dict) -> str:
    for path in schema.get("paths", {}):
        if path.endswith("/conversations"):
            return path[: -len("/conversations")]
    return "/v1"


def _resolve_openapi_schema() -> dict[str, Any] | None:
    _settings_cls, create_app = _import_fastapi_integration()
    if create_app is None:
        return None
    app = create_app()
    return app.openapi()


def _build_python_types_sdk() -> str:
    return '''"""Generated type definitions for ai-decision-council API."""

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
'''


def _build_python_sdk(prefix: str) -> str:
    return f'''"""Generated typed Python client for ai-decision-council API."""

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

    for line in block.split("\\n"):
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
    return event_type, event_id, "\\n".join(data_lines)


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
        suffix = f" (request_id={{request_id}})" if request_id else ""
        super().__init__(f"{{code}}: {{message}}{{suffix}}")


class CouncilApiClient:
    def __init__(self, base_url: str, token: str, timeout: float = 60.0):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        return {{
            "Authorization": f"Bearer {{self.token}}",
            "Content-Type": "application/json",
        }}

    @staticmethod
    def _extract_error(payload: ApiEnvelope) -> tuple[str, str, str | None]:
        errors = payload.get("errors", [])
        if isinstance(errors, list) and errors:
            first = errors[0] or {{}}
            code = str(first.get("code", "http_error"))
            message = str(first.get("message", "Request failed"))
        else:
            code = "http_error"
            message = "Request failed"

        metadata = payload.get("metadata", {{}})
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
                f"{{self.base_url}}{{path}}",
                headers=self._headers(),
                json=json_body,
            )

        try:
            payload = cast(ApiEnvelope, response.json())
        except ValueError:
            payload = {{"data": None, "metadata": {{}}, "errors": []}}

        if not response.is_success:
            code, message, request_id = self._extract_error(payload)
            if request_id is None:
                request_id = response.headers.get("x-request-id")
            raise CouncilApiError(response.status_code, code, message, request_id)
        return payload

    async def list_conversations(self) -> list[ConversationSummary]:
        payload = await self._request("GET", f"{prefix}/conversations")
        data = payload.get("data") or {{}}
        if not isinstance(data, dict):
            return []
        conversations = data.get("conversations", [])
        if not isinstance(conversations, list):
            return []
        return cast(list[ConversationSummary], conversations)

    async def create_conversation(self) -> Conversation:
        payload = await self._request("POST", f"{prefix}/conversations")
        data = payload.get("data") or {{}}
        if not isinstance(data, dict):
            return cast(Conversation, {{}})
        conversation = data.get("conversation", {{}})
        return cast(Conversation, conversation if isinstance(conversation, dict) else {{}})

    async def get_conversation(self, conversation_id: str) -> Conversation:
        payload = await self._request("GET", f"{prefix}/conversations/{{conversation_id}}")
        data = payload.get("data") or {{}}
        if not isinstance(data, dict):
            return cast(Conversation, {{}})
        conversation = data.get("conversation", {{}})
        return cast(Conversation, conversation if isinstance(conversation, dict) else {{}})

    async def send_message(self, conversation_id: str, content: str) -> SendMessageData:
        payload = await self._request(
            "POST",
            f"{prefix}/conversations/{{conversation_id}}/message",
            json_body={{"content": content}},
        )
        data = payload.get("data") or {{}}
        return cast(SendMessageData, data if isinstance(data, dict) else {{}})

    async def send_message_stream(
        self,
        conversation_id: str,
        content: str,
    ) -> AsyncIterator[StreamEvent]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async with client.stream(
                "POST",
                f"{{self.base_url}}{prefix}/conversations/{{conversation_id}}/message/stream",
                headers=self._headers(),
                json={{"content": content}},
            ) as response:
                if not response.is_success:
                    body = await response.aread()
                    try:
                        payload = cast(ApiEnvelope, json.loads(body.decode("utf-8")))
                    except Exception:
                        payload = {{"data": None, "metadata": {{}}, "errors": []}}
                    code, message, request_id = self._extract_error(payload)
                    if request_id is None:
                        request_id = response.headers.get("x-request-id")
                    raise CouncilApiError(response.status_code, code, message, request_id)

                buffer = ""
                async for chunk in response.aiter_text():
                    buffer += chunk.replace("\\r\\n", "\\n")
                    while "\\n\\n" in buffer:
                        block, buffer = buffer.split("\\n\\n", 1)
                        parsed = _parse_sse_block(block)
                        if parsed is None:
                            continue
                        event_type, event_id, data_text = parsed
                        try:
                            envelope = cast(ApiEnvelope, json.loads(data_text))
                        except json.JSONDecodeError:
                            continue
                        yield {{
                            "event_type": event_type,
                            "event_id": event_id,
                            "envelope": envelope,
                        }}
'''


def _build_python_sdk_package() -> str:
    return """from .council_api_client import CouncilApiClient, CouncilApiError
from .council_api_types import (
    ApiEnvelope,
    ApiError,
    AssistantMessage,
    Conversation,
    ConversationSummary,
    SendMessageData,
    StreamEvent,
)

__all__ = [
    "CouncilApiClient",
    "CouncilApiError",
    "ApiEnvelope",
    "ApiError",
    "AssistantMessage",
    "Conversation",
    "ConversationSummary",
    "SendMessageData",
    "StreamEvent",
]
"""


def _build_typescript_types_sdk() -> str:
    return """// Generated type definitions for ai-decision-council API.

export interface ApiError {
  code: string;
  message: string;
}

export interface ApiEnvelope<TData = unknown> {
  data: TData | null;
  metadata: Record<string, unknown>;
  errors: ApiError[];
}

export interface ConversationSummary {
  id: string;
  created_at: string;
  title: string;
  message_count: number;
}

export interface Conversation {
  id: string;
  created_at: string;
  title: string;
  messages: Record<string, unknown>[];
}

export interface AssistantMessage {
  id?: string;
  role?: string;
  stage1?: Record<string, unknown>[];
  stage2?: Record<string, unknown>[];
  stage3?: Record<string, unknown>;
  metadata?: Record<string, unknown>;
  errors?: ApiError[];
  created_at?: string;
}

export interface SendMessageData {
  conversation?: Conversation;
  assistant_message?: AssistantMessage;
  result?: Record<string, unknown>;
}

export interface StreamEvent<TData = unknown> {
  eventType: string;
  eventId: string | null;
  envelope: ApiEnvelope<TData>;
}
"""


def _build_typescript_sdk(prefix: str) -> str:
    return f"""// Generated typed TypeScript client for ai-decision-council API.

import type {{
  ApiEnvelope,
  Conversation,
  ConversationSummary,
  SendMessageData,
  StreamEvent,
}} from './councilApiTypes';

type FetchLike = typeof fetch;

function parseSseBlock(block: string): {{ eventType: string; eventId: string | null; data: string }} | null {{
  let eventType = 'message';
  let eventId: string | null = null;
  const dataLines: string[] = [];

  for (const rawLine of block.split('\\n')) {{
    const line = rawLine.trimEnd();
    if (!line || line.startsWith(':')) {{
      continue;
    }}
    if (line.startsWith('event:')) {{
      eventType = line.slice(6).trim() || 'message';
      continue;
    }}
    if (line.startsWith('id:')) {{
      eventId = line.slice(3).trim() || null;
      continue;
    }}
    if (line.startsWith('data:')) {{
      dataLines.push(line.slice(5).trimStart());
    }}
  }}

  if (dataLines.length === 0) {{
    return null;
  }}

  return {{
    eventType,
    eventId,
    data: dataLines.join('\\n'),
  }};
}}

export class CouncilApiError extends Error {{
  readonly statusCode: number;
  readonly code: string;
  readonly requestId?: string;

  constructor(statusCode: number, code: string, message: string, requestId?: string) {{
    super(`${{code}}: ${{message}}${{requestId ? ` (request_id=${{requestId}})` : ''}}`);
    this.statusCode = statusCode;
    this.code = code;
    this.requestId = requestId;
  }}
}}

export class CouncilApiClient {{
  private readonly baseUrl: string;
  private readonly token: string;
  private readonly fetchImpl: FetchLike;

  constructor(baseUrl: string, token: string, fetchImpl: FetchLike = fetch) {{
    this.baseUrl = baseUrl.replace(/\\/$/, '');
    this.token = token;
    this.fetchImpl = fetchImpl;
  }}

  private headers(extra?: HeadersInit): Headers {{
    const headers = new Headers(extra ?? undefined);
    headers.set('Authorization', `Bearer ${{this.token}}`);
    headers.set('Content-Type', 'application/json');
    return headers;
  }}

  private static extractError<TData>(payload: ApiEnvelope<TData>): {{ code: string; message: string; requestId?: string }} {{
    const first = payload.errors?.[0];
    const requestId =
      (payload.metadata?.['request_id'] as string | undefined) ??
      undefined;
    return {{
      code: first?.code ?? 'http_error',
      message: first?.message ?? 'Request failed',
      requestId,
    }};
  }}

  private async request<TData>(path: string, init?: RequestInit): Promise<ApiEnvelope<TData>> {{
    const response = await this.fetchImpl(`${{this.baseUrl}}${{path}}`, {{
      ...init,
      headers: this.headers(init?.headers),
    }});

    let payload: ApiEnvelope<TData>;
    try {{
      payload = (await response.json()) as ApiEnvelope<TData>;
    }} catch {{
      payload = {{ data: null, metadata: {{}}, errors: [] }};
    }}

    if (!response.ok) {{
      const err = CouncilApiClient.extractError(payload);
      throw new CouncilApiError(
        response.status,
        err.code,
        err.message,
        err.requestId ?? response.headers.get('x-request-id') ?? undefined
      );
    }}
    return payload;
  }}

  async listConversations(): Promise<ConversationSummary[]> {{
    const payload = await this.request<{{ conversations?: ConversationSummary[] }}>(`{prefix}/conversations`);
    return payload.data?.conversations ?? [];
  }}

  async createConversation(): Promise<Conversation> {{
    const payload = await this.request<{{ conversation?: Conversation }}>(`{prefix}/conversations`, {{
      method: 'POST',
    }});
    return payload.data?.conversation ?? ({{}} as Conversation);
  }}

  async getConversation(conversationId: string): Promise<Conversation> {{
    const payload = await this.request<{{ conversation?: Conversation }}>(
      `{prefix}/conversations/${{conversationId}}`
    );
    return payload.data?.conversation ?? ({{}} as Conversation);
  }}

  async sendMessage(conversationId: string, content: string): Promise<SendMessageData> {{
    const payload = await this.request<SendMessageData>(
      `{prefix}/conversations/${{conversationId}}/message`,
      {{
        method: 'POST',
        body: JSON.stringify({{ content }}),
      }}
    );
    return payload.data ?? {{}};
  }}

  async *sendMessageStream(
    conversationId: string,
    content: string
  ): AsyncGenerator<StreamEvent> {{
    const response = await this.fetchImpl(
      `${{this.baseUrl}}{prefix}/conversations/${{conversationId}}/message/stream`,
      {{
        method: 'POST',
        headers: this.headers(),
        body: JSON.stringify({{ content }}),
      }}
    );

    if (!response.ok) {{
      let payload: ApiEnvelope<unknown> = {{ data: null, metadata: {{}}, errors: [] }};
      try {{
        payload = (await response.json()) as ApiEnvelope<unknown>;
      }} catch {{
        // keep fallback payload
      }}
      const err = CouncilApiClient.extractError(payload);
      throw new CouncilApiError(
        response.status,
        err.code,
        err.message,
        err.requestId ?? response.headers.get('x-request-id') ?? undefined
      );
    }}

    if (!response.body) {{
      throw new Error('Streaming is not supported in this runtime.');
    }}

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {{
      const {{ done, value }} = await reader.read();
      if (done) {{
        buffer += decoder.decode().replace(/\\r\\n/g, '\\n');
      }} else {{
        buffer += decoder.decode(value, {{ stream: true }}).replace(/\\r\\n/g, '\\n');
      }}

      let boundary = buffer.indexOf('\\n\\n');
      while (boundary !== -1) {{
        const block = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        boundary = buffer.indexOf('\\n\\n');

        const parsed = parseSseBlock(block);
        if (!parsed) {{
          continue;
        }}
        try {{
          const envelope = JSON.parse(parsed.data) as ApiEnvelope<unknown>;
          yield {{
            eventType: parsed.eventType,
            eventId: parsed.eventId,
            envelope,
          }};
        }} catch {{
          // ignore malformed event chunks
        }}
      }}

      if (done) {{
        break;
      }}
    }}
  }}
}}
"""


def _build_typescript_sdk_index() -> str:
    return """export * from './councilApiClient';
export * from './councilApiTypes';
"""


def _write_sdk_files(output_dir: Path, *, prefix: str, force: bool) -> bool:
    output_dir.mkdir(parents=True, exist_ok=True)
    files = [
        (output_dir / "council_api_client.py", _build_python_sdk(prefix)),
        (output_dir / "council_api_types.py", _build_python_types_sdk()),
        (output_dir / "__init__.py", _build_python_sdk_package()),
        (output_dir / "councilApiClient.ts", _build_typescript_sdk(prefix)),
        (output_dir / "councilApiTypes.ts", _build_typescript_types_sdk()),
        (output_dir / "index.ts", _build_typescript_sdk_index()),
    ]
    wrote = [_write_file(path, content, force=force) for path, content in files]
    return all(wrote)


def cmd_api_sdk(args: argparse.Namespace) -> int:
    load_dotenv()
    schema = _resolve_openapi_schema()
    if schema is None:
        return 1

    prefix = _detect_api_prefix(schema)
    output_dir = Path(args.output_dir).resolve()
    success = _write_sdk_files(output_dir, prefix=prefix, force=args.force)
    return 0 if success else 1


def _render_bootstrap_env(*, api_key: str, api_token: str) -> str:
    resolved_key = api_key.strip() if api_key.strip() else "replace-me"
    return f"""# Generated by `ai-decision-council api bootstrap`
# Replace API key if this file contains `replace-me`.
LLM_COUNCIL_API_KEY={resolved_key}
LLM_COUNCIL_REFERENCE_API_TOKEN={api_token}
VITE_REFERENCE_API_TOKEN={api_token}
LLM_COUNCIL_MODEL_COUNT=5
LLM_COUNCIL_API_PREFIX=/v1
"""


def cmd_api_bootstrap(args: argparse.Namespace) -> int:
    load_dotenv()
    target_dir = Path(args.path).resolve()

    init_args = argparse.Namespace(path=str(target_dir), api=args.api_scaffold, force=args.force)
    if cmd_init(init_args) != 0:
        return 1

    api_key = os.getenv("LLM_COUNCIL_API_KEY") or os.getenv("OPENROUTER_API_KEY") or ""
    api_token = os.getenv("LLM_COUNCIL_REFERENCE_API_TOKEN") or secrets.token_urlsafe(24)
    wrote_env = _write_file(
        target_dir / ".env",
        _render_bootstrap_env(api_key=api_key, api_token=api_token),
        force=args.force,
    )
    if not wrote_env:
        return 1

    if args.skip_openapi and args.skip_sdk:
        return 0

    schema = _resolve_openapi_schema()
    if schema is None:
        return 1

    if not args.skip_openapi:
        wrote_openapi = _write_file(
            target_dir / args.openapi_output,
            json.dumps(schema, indent=2) + "\n",
            force=args.force,
        )
        if not wrote_openapi:
            return 1

    if not args.skip_sdk:
        prefix = _detect_api_prefix(schema)
        wrote_sdk = _write_sdk_files(
            (target_dir / args.sdk_dir).resolve(),
            prefix=prefix,
            force=args.force,
        )
        if not wrote_sdk:
            return 1

    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ai-decision-council",
        description="CLI for integrating and running the ai-decision-council package.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser(
        "init",
        help="Create integration starter files in your project.",
    )
    init_parser.add_argument(
        "--path",
        default=".",
        help="Target directory for generated files.",
    )
    init_parser.add_argument(
        "--api",
        choices=["bridge", "fastapi", "all"],
        default="bridge",
        help="Scaffold target. `fastapi` creates API module templates.",
    )
    init_parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing files.",
    )
    init_parser.set_defaults(func=cmd_init)

    bridge_parser = subparsers.add_parser(
        "bridge",
        help="Generate a project-local bridge module.",
    )
    bridge_parser.add_argument(
        "--output",
        default="ai_decision_council_bridge.py",
        help="Path to generated bridge file.",
    )
    bridge_parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing file.",
    )
    bridge_parser.set_defaults(func=cmd_bridge)

    doctor_parser = subparsers.add_parser(
        "doctor",
        help="Validate required runtime configuration.",
    )
    doctor_parser.set_defaults(func=cmd_doctor)

    models_parser = subparsers.add_parser(
        "models",
        help="Print default or currently selected model set.",
    )
    models_parser.add_argument(
        "--defaults",
        action="store_true",
        help="Show curated default model catalog.",
    )
    models_parser.add_argument(
        "--count",
        type=int,
        help="When used with --defaults, show only first N default models.",
    )
    models_parser.set_defaults(func=cmd_models)

    run_parser = subparsers.add_parser(
        "run",
        help="Run the council pipeline for a single prompt.",
    )
    run_parser.add_argument(
        "--prompt",
        "-p",
        required=True,
        help="Prompt to send through the council.",
    )
    run_parser.add_argument(
        "--json",
        action="store_true",
        help="Print full structured output as JSON.",
    )
    run_parser.set_defaults(func=cmd_run)

    api_parser = subparsers.add_parser(
        "api",
        help="FastAPI integration utilities (bootstrap, serve, schema, SDK).",
    )
    api_subparsers = api_parser.add_subparsers(dest="api_command", required=True)

    bootstrap_parser = api_subparsers.add_parser(
        "bootstrap",
        help="One-command setup: scaffold files, write .env, generate OpenAPI and typed SDK.",
    )
    bootstrap_parser.add_argument(
        "--path",
        default=".",
        help="Target directory for generated files and artifacts.",
    )
    bootstrap_parser.add_argument(
        "--api-scaffold",
        choices=["bridge", "fastapi", "all"],
        default="all",
        help="Which integration files to scaffold before generating artifacts.",
    )
    bootstrap_parser.add_argument(
        "--openapi-output",
        default="openapi.json",
        help="OpenAPI output path relative to --path.",
    )
    bootstrap_parser.add_argument(
        "--sdk-dir",
        default="sdk",
        help="SDK output directory relative to --path.",
    )
    bootstrap_parser.add_argument(
        "--skip-openapi",
        action="store_true",
        help="Skip OpenAPI schema generation.",
    )
    bootstrap_parser.add_argument(
        "--skip-sdk",
        action="store_true",
        help="Skip SDK generation.",
    )
    bootstrap_parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing files.",
    )
    bootstrap_parser.set_defaults(func=cmd_api_bootstrap)

    serve_parser = api_subparsers.add_parser("serve", help="Run the packaged FastAPI app.")
    serve_parser.add_argument("--host", default="0.0.0.0")
    serve_parser.add_argument("--port", type=int, default=8001)
    serve_parser.add_argument("--reload", action="store_true")
    serve_parser.set_defaults(func=cmd_api_serve)

    openapi_parser = api_subparsers.add_parser(
        "openapi",
        help="Write OpenAPI schema from packaged FastAPI app.",
    )
    openapi_parser.add_argument(
        "--output",
        default="ai_decision_council_openapi.json",
        help="Path to generated OpenAPI JSON file.",
    )
    openapi_parser.add_argument("--force", action="store_true")
    openapi_parser.set_defaults(func=cmd_api_openapi)

    sdk_parser = api_subparsers.add_parser(
        "sdk",
        help="Generate typed Python + TypeScript SDK clients from OpenAPI contract.",
    )
    sdk_parser.add_argument(
        "--output-dir",
        default="./sdk",
        help="Directory where SDK files will be created.",
    )
    sdk_parser.add_argument("--force", action="store_true")
    sdk_parser.set_defaults(func=cmd_api_sdk)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)
