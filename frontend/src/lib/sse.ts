/**
 * A buffered Server-Sent-Events frame parser over a fetch `Response`.
 *
 * Not `EventSource`: chat's stream needs `POST` with a body (EventSource is
 * GET-only), and jsdom (the vitest environment) has no `EventSource` at all,
 * while `fetch`/`ReadableStream` are real Node globals already exercised in
 * this codebase's tests — one shared, easily-mocked code path.
 */
export interface SseEvent {
  event: string;
  data: unknown;
}

/** Parse one `\n`-delimited SSE frame; `null` for a frame with no data line. */
function parseFrame(frame: string): SseEvent | null {
  let event = "message";
  let data: string | undefined;
  for (const line of frame.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) data = line.slice(5).trim();
  }
  if (data === undefined) return null;
  try {
    return { event, data: JSON.parse(data) };
  } catch {
    // Malformed frame (e.g. a keep-alive comment misparsed) — skip it rather
    // than killing the whole stream over one bad event.
    return null;
  }
}

export async function* parseSse(response: Response): AsyncGenerator<SseEvent> {
  const reader = response.body?.getReader();
  if (!reader) return;

  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) return;
    buffer += decoder.decode(value, { stream: true });

    let separator: number;
    while ((separator = buffer.indexOf("\n\n")) !== -1) {
      const frame = buffer.slice(0, separator);
      buffer = buffer.slice(separator + 2);
      const event = parseFrame(frame);
      if (event) yield event;
    }
  }
}
