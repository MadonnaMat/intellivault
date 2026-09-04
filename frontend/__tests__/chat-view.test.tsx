import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ChatView } from "@/app/chat/chat-view";

const user = { id: "u1", email: "ada@example.com", display_name: "Ada" };

function sse(events: Array<Record<string, unknown>>): string {
  return events.map((event) => `data: ${JSON.stringify(event)}\n\n`).join("") + "data: [DONE]\n\n";
}

function mockChatResponse(body: string) {
  return vi
    .spyOn(globalThis, "fetch")
    .mockResolvedValue(new Response(body, { status: 200, headers: { "content-type": "text/event-stream" } }));
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

async function sendMessage(text: string) {
  fireEvent.change(screen.getByTestId("chat-input"), { target: { value: text } });
  fireEvent.click(screen.getByTestId("chat-send"));
}

describe("ChatView", () => {
  it("renders a streamed reply as markdown", async () => {
    mockChatResponse(
      sse([
        {
          type: "update-state",
          operations: [
            {
              type: "set",
              path: ["messages", "0"],
              value: { role: "user", parts: [{ type: "text", text: "Hi" }] },
            },
          ],
        },
        {
          type: "update-state",
          operations: [
            {
              type: "set",
              path: ["messages", "1"],
              value: { role: "assistant", parts: [{ type: "text", text: "**Hello**" }] },
            },
          ],
        },
      ]),
    );

    render(<ChatView user={user} />);
    await sendMessage("Hi");

    await waitFor(() => expect(screen.getByTestId("chat-message-list")).toHaveTextContent("Hi"));
    await waitFor(() =>
      expect(screen.getByTestId("chat-message-list")).toHaveTextContent("Hello"),
    );
    // react-markdown renders **Hello** as a real <strong>, not literal asterisks.
    expect(screen.getByText("Hello").tagName).toBe("STRONG");
  });

  it("shows a run card for a resolved launch_research_agent tool call", async () => {
    mockChatResponse(
      sse([
        {
          type: "update-state",
          operations: [
            {
              type: "set",
              path: ["messages", "0"],
              value: { role: "user", parts: [{ type: "text", text: "Research the transistor" }] },
            },
          ],
        },
        {
          type: "update-state",
          operations: [
            {
              type: "set",
              path: ["messages", "1"],
              value: {
                role: "assistant",
                parts: [
                  { type: "text", text: "On it!" },
                  {
                    type: "tool-call",
                    toolCallId: "launch-abc",
                    toolName: "launch_research_agent",
                    args: { topic: "the transistor" },
                    argsText: '{"topic":"the transistor"}',
                    done: true,
                    result: { id: "abc-123", topic: "the transistor", status: "queued" },
                  },
                ],
              },
            },
          ],
        },
      ]),
    );

    render(<ChatView user={user} />);
    await sendMessage("Research the transistor");

    const runCard = await screen.findByTestId("chat-run-card");
    expect(runCard).toHaveTextContent("the transistor");
    expect(runCard).toHaveTextContent("queued");
    expect(screen.getByRole("link", { name: /view progress/i })).toHaveAttribute(
      "href",
      "/runs/abc-123",
    );
  });

  it("shows a search card for a resolved search_knowledge_graph tool call", async () => {
    mockChatResponse(
      sse([
        {
          type: "update-state",
          operations: [
            {
              type: "set",
              path: ["messages", "0"],
              value: { role: "user", parts: [{ type: "text", text: "What do we know?" }] },
            },
          ],
        },
        {
          type: "update-state",
          operations: [
            {
              type: "set",
              path: ["messages", "1"],
              value: {
                role: "assistant",
                parts: [
                  { type: "text", text: "Here's what I found." },
                  {
                    type: "tool-call",
                    toolCallId: "search-abc",
                    toolName: "search_knowledge_graph",
                    args: { query: "the transistor" },
                    argsText: '{"query":"the transistor"}',
                    done: true,
                    result: {
                      entities: [{ id: "e1", name: "Bell Labs", kind: "org" }],
                      relationships: [],
                    },
                  },
                ],
              },
            },
          ],
        },
      ]),
    );

    render(<ChatView user={user} />);
    await sendMessage("What do we know?");

    const searchCard = await screen.findByTestId("chat-search-card");
    expect(searchCard).toHaveTextContent("the transistor");
    expect(searchCard).toHaveTextContent("Bell Labs");
  });

  it("surfaces a transport error", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("boom", { status: 500 }));

    render(<ChatView user={user} />);
    await sendMessage("Hi");

    expect(await screen.findByTestId("chat-error")).toBeInTheDocument();
  });
});
