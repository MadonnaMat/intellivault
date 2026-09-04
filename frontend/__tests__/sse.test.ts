import { describe, expect, it } from "vitest";
import { parseSse } from "@/lib/sse";

function streamOf(chunks: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  let i = 0;
  return new ReadableStream({
    pull(controller) {
      if (i < chunks.length) {
        controller.enqueue(encoder.encode(chunks[i]));
        i += 1;
      } else {
        controller.close();
      }
    },
  });
}

function responseOf(chunks: string[]): Response {
  return new Response(streamOf(chunks));
}

async function collect(response: Response) {
  const events = [];
  for await (const event of parseSse(response)) events.push(event);
  return events;
}

describe("parseSse", () => {
  it("parses a single complete frame", async () => {
    const response = responseOf(['event: status\ndata: {"a": 1}\n\n']);
    expect(await collect(response)).toEqual([{ event: "status", data: { a: 1 } }]);
  });

  it("parses multiple frames from one chunk", async () => {
    const response = responseOf([
      'event: a\ndata: 1\n\nevent: b\ndata: 2\n\n',
    ]);
    expect(await collect(response)).toEqual([
      { event: "a", data: 1 },
      { event: "b", data: 2 },
    ]);
  });

  it("reassembles a frame split across two read() calls", async () => {
    const response = responseOf(['event: status\ndata: {"a"', ': 1}\n\n']);
    expect(await collect(response)).toEqual([{ event: "status", data: { a: 1 } }]);
  });

  it("defaults to event: message when no event line is present", async () => {
    const response = responseOf(["data: 42\n\n"]);
    expect(await collect(response)).toEqual([{ event: "message", data: 42 }]);
  });

  it("skips a malformed data line instead of throwing", async () => {
    const response = responseOf(["data: not-json\n\ndata: 1\n\n"]);
    expect(await collect(response)).toEqual([{ event: "message", data: 1 }]);
  });

  it("ignores a keep-alive comment line", async () => {
    const response = responseOf([": heartbeat\n\ndata: 1\n\n"]);
    expect(await collect(response)).toEqual([{ event: "message", data: 1 }]);
  });

  it("yields nothing for a response with no body", async () => {
    const response = new Response(null);
    expect(await collect(response)).toEqual([]);
  });
});
