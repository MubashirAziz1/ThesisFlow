export interface SseEvent {
  event: string;
  data: string;
  id?: string;
}

const FRAME_SEPARATOR = /\r?\n\r?\n/;

function parseFrame(frame: string): SseEvent | null {
  if (!frame.trim()) return null;

  let event = "message";
  let id: string | undefined;
  const dataLines: string[] = [];

  for (const line of frame.split(/\r?\n/)) {
    if (!line || line.startsWith(":")) continue; // comment / heartbeat
    const colon = line.indexOf(":");
    const field = colon === -1 ? line : line.slice(0, colon);
    let value = colon === -1 ? "" : line.slice(colon + 1);
    if (value.startsWith(" ")) value = value.slice(1);

    if (field === "event") event = value;
    else if (field === "data") dataLines.push(value);
    else if (field === "id") id = value;
  }

  return { event, data: dataLines.join("\n"), id };
}

/**
 * Incrementally parse a `text/event-stream` body, invoking `onEvent` for each
 * complete frame as it arrives (this is what makes streaming render in real
 * time). Comment-only lines such as `: heartbeat` are discarded.
 */
export async function readSseStream(
  body: ReadableStream<Uint8Array>,
  onEvent: (event: SseEvent) => void,
): Promise<void> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      let match: RegExpExecArray | null;
      while ((match = FRAME_SEPARATOR.exec(buffer)) !== null) {
        const frame = buffer.slice(0, match.index);
        buffer = buffer.slice(match.index + match[0].length);
        const parsed = parseFrame(frame);
        if (parsed) onEvent(parsed);
      }
    }
  } finally {
    reader.releaseLock();
  }

  buffer += decoder.decode();
  const trailing = parseFrame(buffer);
  if (trailing) onEvent(trailing);
}
