"""SDK builder functions for CLI scaffold commands."""

from __future__ import annotations

from pathlib import Path

from ._cli_utils import _write_file


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

