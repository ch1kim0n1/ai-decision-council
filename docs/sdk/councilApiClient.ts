// Generated typed TypeScript client for ai-decision-council API.

import type {
  ApiEnvelope,
  Conversation,
  ConversationSummary,
  SendMessageData,
  StreamEvent,
} from './councilApiTypes';

type FetchLike = typeof fetch;

function parseSseBlock(block: string): { eventType: string; eventId: string | null; data: string } | null {
  let eventType = 'message';
  let eventId: string | null = null;
  const dataLines: string[] = [];

  for (const rawLine of block.split('\n')) {
    const line = rawLine.trimEnd();
    if (!line || line.startsWith(':')) {
      continue;
    }
    if (line.startsWith('event:')) {
      eventType = line.slice(6).trim() || 'message';
      continue;
    }
    if (line.startsWith('id:')) {
      eventId = line.slice(3).trim() || null;
      continue;
    }
    if (line.startsWith('data:')) {
      dataLines.push(line.slice(5).trimStart());
    }
  }

  if (dataLines.length === 0) {
    return null;
  }

  return {
    eventType,
    eventId,
    data: dataLines.join('\n'),
  };
}

export class CouncilApiError extends Error {
  readonly statusCode: number;
  readonly code: string;
  readonly requestId?: string;

  constructor(statusCode: number, code: string, message: string, requestId?: string) {
    super(`${code}: ${message}${requestId ? ` (request_id=${requestId})` : ''}`);
    this.statusCode = statusCode;
    this.code = code;
    this.requestId = requestId;
  }
}

export class CouncilApiClient {
  private readonly baseUrl: string;
  private readonly token: string;
  private readonly fetchImpl: FetchLike;

  constructor(baseUrl: string, token: string, fetchImpl: FetchLike = fetch) {
    this.baseUrl = baseUrl.replace(/\/$/, '');
    this.token = token;
    this.fetchImpl = fetchImpl;
  }

  private headers(extra?: HeadersInit): Headers {
    const headers = new Headers(extra ?? undefined);
    headers.set('Authorization', `Bearer ${this.token}`);
    headers.set('Content-Type', 'application/json');
    return headers;
  }

  private static extractError<TData>(payload: ApiEnvelope<TData>): { code: string; message: string; requestId?: string } {
    const first = payload.errors?.[0];
    const requestId =
      (payload.metadata?.['request_id'] as string | undefined) ??
      undefined;
    return {
      code: first?.code ?? 'http_error',
      message: first?.message ?? 'Request failed',
      requestId,
    };
  }

  private async request<TData>(path: string, init?: RequestInit): Promise<ApiEnvelope<TData>> {
    const response = await this.fetchImpl(`${this.baseUrl}${path}`, {
      ...init,
      headers: this.headers(init?.headers),
    });

    let payload: ApiEnvelope<TData>;
    try {
      payload = (await response.json()) as ApiEnvelope<TData>;
    } catch {
      payload = { data: null, metadata: {}, errors: [] };
    }

    if (!response.ok) {
      const err = CouncilApiClient.extractError(payload);
      throw new CouncilApiError(
        response.status,
        err.code,
        err.message,
        err.requestId ?? response.headers.get('x-request-id') ?? undefined
      );
    }
    return payload;
  }

  async listConversations(): Promise<ConversationSummary[]> {
    const payload = await this.request<{ conversations?: ConversationSummary[] }>(`/v1/conversations`);
    return payload.data?.conversations ?? [];
  }

  async createConversation(): Promise<Conversation> {
    const payload = await this.request<{ conversation?: Conversation }>(`/v1/conversations`, {
      method: 'POST',
    });
    return payload.data?.conversation ?? ({} as Conversation);
  }

  async getConversation(conversationId: string): Promise<Conversation> {
    const payload = await this.request<{ conversation?: Conversation }>(
      `/v1/conversations/${conversationId}`
    );
    return payload.data?.conversation ?? ({} as Conversation);
  }

  async sendMessage(conversationId: string, content: string): Promise<SendMessageData> {
    const payload = await this.request<SendMessageData>(
      `/v1/conversations/${conversationId}/message`,
      {
        method: 'POST',
        body: JSON.stringify({ content }),
      }
    );
    return payload.data ?? {};
  }

  async *sendMessageStream(
    conversationId: string,
    content: string
  ): AsyncGenerator<StreamEvent> {
    const response = await this.fetchImpl(
      `${this.baseUrl}/v1/conversations/${conversationId}/message/stream`,
      {
        method: 'POST',
        headers: this.headers(),
        body: JSON.stringify({ content }),
      }
    );

    if (!response.ok) {
      let payload: ApiEnvelope<unknown> = { data: null, metadata: {}, errors: [] };
      try {
        payload = (await response.json()) as ApiEnvelope<unknown>;
      } catch {
        // keep fallback payload
      }
      const err = CouncilApiClient.extractError(payload);
      throw new CouncilApiError(
        response.status,
        err.code,
        err.message,
        err.requestId ?? response.headers.get('x-request-id') ?? undefined
      );
    }

    if (!response.body) {
      throw new Error('Streaming is not supported in this runtime.');
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) {
        buffer += decoder.decode().replace(/\r\n/g, '\n');
      } else {
        buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, '\n');
      }

      let boundary = buffer.indexOf('\n\n');
      while (boundary !== -1) {
        const block = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        boundary = buffer.indexOf('\n\n');

        const parsed = parseSseBlock(block);
        if (!parsed) {
          continue;
        }
        try {
          const envelope = JSON.parse(parsed.data) as ApiEnvelope<unknown>;
          yield {
            eventType: parsed.eventType,
            eventId: parsed.eventId,
            envelope,
          };
        } catch {
          // ignore malformed event chunks
        }
      }

      if (done) {
        break;
      }
    }
  }
}
