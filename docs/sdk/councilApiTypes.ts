// Generated type definitions for ai-decision-council API.

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
