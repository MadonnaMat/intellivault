import { afterEach, describe, expect, it, vi } from "vitest";

const { cookieGet } = vi.hoisted(() => ({ cookieGet: vi.fn() }));

vi.mock("next/headers", () => ({ cookies: async () => ({ get: cookieGet }) }));

import { POST } from "@/app/api/chat/route";
import { SESSION_COOKIE, serverBackendUrl } from "@/lib/backend";

afterEach(() => {
  vi.clearAllMocks();
  vi.restoreAllMocks();
});

function chatRequest(body: unknown): Request {
  return new Request("http://localhost:3000/api/chat", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

describe("POST /api/chat", () => {
  it("401s without forwarding when there is no session cookie", async () => {
    cookieGet.mockReturnValue(undefined);
    const fetchMock = vi.spyOn(globalThis, "fetch");

    const response = await POST(chatRequest({ commands: [] }));

    expect(response.status).toBe(401);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("forwards the body and session cookie to the backend, streaming the response back", async () => {
    cookieGet.mockReturnValue({ value: "tok-123" });
    const sseBody = 'data: {"type": "update-state", "operations": []}\n\ndata: [DONE]\n\n';
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(
        new Response(sseBody, { status: 200, headers: { "content-type": "text/event-stream" } }),
      );

    const body = { commands: [{ type: "add-message", message: { role: "user", parts: [] } }] };
    const response = await POST(chatRequest(body));

    expect(fetchMock).toHaveBeenCalledWith(
      `${serverBackendUrl}/chat`,
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify(body),
        headers: expect.objectContaining({
          cookie: `${SESSION_COOKIE}=tok-123`,
          "content-type": "application/json",
        }),
      }),
    );
    expect(response.status).toBe(200);
    expect(response.headers.get("content-type")).toBe("text/event-stream");
    await expect(response.text()).resolves.toBe(sseBody);
  });

  it("propagates the backend's status on failure", async () => {
    cookieGet.mockReturnValue({ value: "tok-123" });
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("nope", { status: 500 }));

    const response = await POST(chatRequest({ commands: [] }));

    expect(response.status).toBe(500);
  });
});
