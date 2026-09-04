"use client";

import { useState } from "react";
import {
  useAssistantTransportRuntime,
  type AssistantRuntime,
  type AssistantTransportConnectionMetadata,
  type ThreadAssistantMessagePart,
  type ThreadMessage,
  type ThreadUserMessagePart,
} from "@assistant-ui/react";

// The backend's AssistantTransport state shape ({role, parts}) — see
// backend/app/chat/schemas.py. Distinct from assistant-ui's own ThreadMessage,
// which the converter below produces.
export type BackendTextPart = { type: "text"; text: string };
export type BackendToolCallPart = {
  type: "tool-call";
  toolCallId: string;
  toolName: string;
  args?: Record<string, unknown>;
  argsText?: string;
  done?: boolean;
  result?: unknown;
};
export type BackendPart = BackendTextPart | BackendToolCallPart;
export type BackendMessage = { role: "user" | "assistant"; parts: BackendPart[] };
export type ChatState = { messages: BackendMessage[] };

function toThreadMessage(message: BackendMessage, index: number, running: boolean): ThreadMessage {
  const id = `msg-${index}`;
  const createdAt = new Date(index);

  if (message.role === "user") {
    const content: ThreadUserMessagePart[] = message.parts
      .filter((part): part is BackendTextPart => part.type === "text")
      .map((part) => ({ type: "text", text: part.text }));
    return {
      id,
      createdAt,
      role: "user",
      content,
      attachments: [],
      metadata: { custom: {} },
    };
  }

  const content: ThreadAssistantMessagePart[] = message.parts.map((part) => {
    if (part.type === "tool-call") {
      return {
        type: "tool-call",
        toolCallId: part.toolCallId,
        toolName: part.toolName,
        // The backend guarantees this is plain JSON; assistant-ui's stricter
        // ReadonlyJSONObject type isn't exported for us to target directly.
        args: (part.args ?? {}) as unknown,
        argsText: part.argsText ?? "",
        result: part.result,
      } as unknown as ThreadAssistantMessagePart;
    }
    return { type: "text", text: part.text };
  });

  return {
    id,
    createdAt,
    role: "assistant",
    content,
    status: running ? { type: "running" } : { type: "complete", reason: "stop" },
    metadata: {
      unstable_state: null,
      unstable_annotations: [],
      unstable_data: [],
      steps: [],
      custom: {},
    },
  };
}

function toThreadMessages(state: ChatState, isSending: boolean): ThreadMessage[] {
  const lastIndex = state.messages.length - 1;
  return state.messages.map((message, index) =>
    toThreadMessage(message, index, isSending && index === lastIndex),
  );
}

export function useChatRuntime(): { runtime: AssistantRuntime; error: string | null } {
  const [error, setError] = useState<string | null>(null);

  const runtime = useAssistantTransportRuntime<ChatState>({
    initialState: { messages: [] },
    api: "/api/chat",
    // Matches AssistantTransportResponse's SSE encoding on the backend — the
    // hook's default ("data-stream") is a different wire format.
    protocol: "assistant-transport",
    headers: {},
    converter: (state, connectionMetadata: AssistantTransportConnectionMetadata) => ({
      messages: toThreadMessages(state, connectionMetadata.isSending),
      isRunning: connectionMetadata.isSending,
    }),
    onError: (err) => setError(err.message),
  });

  return { runtime, error };
}
