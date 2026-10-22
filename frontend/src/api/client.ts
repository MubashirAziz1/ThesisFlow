import { readSseStream } from "./sse";
import type {
  MessagesTuplePayload,
  RunErrorEvent,
  RunMetadataEvent,
  WireMessage,
} from "../types";

export async function checkHealth(signal?: AbortSignal): Promise<boolean> {
  try {
    const response = await fetch("/health", { signal });
    return response.ok;
  } catch {
    return false;
  }
}

/**
 * Extract the text delta from a streamed LangChain message chunk.
 *
 * `chunk.content` is either a plain string or a list of content blocks
 * (e.g. `{type: "text", text: "..."}` when the model uses the OpenAI
 * Responses API). Non-text blocks (reasoning, tool calls) carry no
 * user-visible prose here and are skipped.
 */
export function extractTextDelta(payload: MessagesTuplePayload): string {
  const content = payload?.[0]?.content;
  if (typeof content === "string") return content;
  if (Array.isArray(content)) {
    let text = "";
    for (const block of content) {
      if (typeof block === "string") {
        text += block;
      } else if (
        block &&
        typeof block === "object" &&
        (block as { type?: unknown }).type === "text" &&
        typeof (block as { text?: unknown }).text === "string"
      ) {
        text += (block as { text: string }).text;
      }
    }
    return text;
  }
  return "";
}

export interface StreamRunCallbacks {
  onMetadata?: (data: RunMetadataEvent) => void;
  onMessageChunk?: (textDelta: string) => void;
  onErrorEvent?: (error: RunErrorEvent) => void;
  onEnd?: () => void;
}

/**
 * POST /api/threads/{threadId}/runs/stream and consume the SSE stream.
 *
 * Events emitted by the gateway: `metadata`, `messages` (token deltas),
 * `error`, and `end`. Throws on HTTP failure; server-side run failures are
 * reported through `onErrorEvent` instead.
 */
export async function streamRun(
  threadId: string,
  messages: WireMessage[],
  signal: AbortSignal,
  callbacks: StreamRunCallbacks,
): Promise<void> {
  const response = await fetch(
    `/api/threads/${encodeURIComponent(threadId)}/runs/stream`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "text/event-stream",
      },
      body: JSON.stringify({
        input: { messages },
        stream_mode: ["messages-tuple"],
      }),
      signal,
    },
  );

  if (!response.ok) {
    const detail = await response.text().catch(() => "");
    throw new Error(
      `Run request failed (HTTP ${response.status})${detail ? `: ${detail.slice(0, 300)}` : ""}`,
    );
  }
  if (!response.body) {
    throw new Error("The run response has no body to stream.");
  }

  await readSseStream(response.body, (event) => {
    switch (event.event) {
      case "metadata":
        callbacks.onMetadata?.(JSON.parse(event.data) as RunMetadataEvent);
        break;
      case "messages": {
        const payload = JSON.parse(event.data) as MessagesTuplePayload;
        const delta = extractTextDelta(payload);
        if (delta) callbacks.onMessageChunk?.(delta);
        break;
      }
      case "error":
        callbacks.onErrorEvent?.(JSON.parse(event.data) as RunErrorEvent);
        break;
      case "end":
        callbacks.onEnd?.();
        break;
      default:
        break; // unknown events are ignored forward-compatibly
    }
  });
}
