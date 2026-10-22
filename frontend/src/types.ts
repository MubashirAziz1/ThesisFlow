export type ChatRole = "user" | "assistant";

export type MessageStatus = "streaming" | "done" | "error";

export interface ChatMessage {
  id: string;
  role: ChatRole;
  content: string;
  status: MessageStatus;
  createdAt: number;
}

export interface Thread {
  id: string;
  title: string;
  createdAt: number;
  messages: ChatMessage[];
}

export type BackendStatus = "checking" | "online" | "offline";

/** Payload of the SSE `metadata` event. */
export interface RunMetadataEvent {
  run_id: string;
  thread_id: string;
}

/** Payload of the SSE `error` event. */
export interface RunErrorEvent {
  message: string;
  name?: string;
}

/**
 * Payload of the SSE `messages` event: a serialized LangGraph
 * `stream_mode="messages"` tuple — [messageChunk, metadata].
 */
export type MessagesTuplePayload = [
  chunk: { content?: unknown; type?: string },
  metadata: Record<string, unknown>,
];

/** One message in the run request body (LangChain wire format). */
export interface WireMessage {
  role: "user" | "assistant";
  content: string;
}
