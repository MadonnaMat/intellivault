"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  AssistantRuntimeProvider,
  AuiIf,
  ComposerPrimitive,
  MessagePrimitive,
  ThreadPrimitive,
} from "@assistant-ui/react";
import { MarkdownTextPrimitive } from "@assistant-ui/react-markdown";
import { Alert, Card, Tag, Typography } from "antd";
import type { SessionUser } from "@/lib/auth";
import { streamRun, type AgentRunStatus } from "@/lib/agent";
import { useChatRuntime } from "./chat-runtime";

interface LaunchResult {
  id: string;
  topic: string;
  status: AgentRunStatus;
}

const STATUS_COLOR: Record<AgentRunStatus, string> = {
  queued: "default",
  running: "processing",
  awaiting_review: "gold",
  succeeded: "green",
  failed: "red",
  cancelled: "default",
};

function LaunchResearchAgentCard({ result }: { result?: LaunchResult }) {
  const [status, setStatus] = useState<AgentRunStatus | undefined>(result?.status);
  const runId = result?.id;

  useEffect(() => {
    if (!runId) return;
    let cancelled = false;
    async function subscribe(id: string) {
      try {
        for await (const event of streamRun(id)) {
          if (cancelled) return;
          if (event.event === "status") {
            setStatus((event.data as { status: AgentRunStatus }).status);
          }
        }
      } catch {
        // Live updates stop; the card keeps showing the last known status.
      }
    }
    void subscribe(runId);
    return () => {
      cancelled = true;
    };
  }, [runId]);

  if (!result) return null;
  return (
    <Card size="small" data-testid="chat-run-card" style={{ marginTop: 8, maxWidth: 320 }}>
      <Typography.Text strong>Researching: {result.topic}</Typography.Text>
      <div style={{ marginTop: 4 }}>
        <Tag color={STATUS_COLOR[status ?? result.status]}>{status ?? result.status}</Tag>
      </div>
      <Link href={`/runs/${result.id}`}>View progress</Link>
    </Card>
  );
}

function MarkdownText() {
  // MarkdownTextPrimitive reads the current part from context, not props —
  // this wrapper is what makes it slot into MessagePrimitive.Parts's `Text`.
  return <MarkdownTextPrimitive />;
}

function UserMessage() {
  return (
    <MessagePrimitive.Root style={{ display: "flex", justifyContent: "flex-end" }}>
      <div
        style={{
          maxWidth: "80%",
          background: "#1677ff",
          color: "#fff",
          borderRadius: 16,
          padding: "8px 14px",
        }}
      >
        <MessagePrimitive.Parts />
      </div>
    </MessagePrimitive.Root>
  );
}

function AssistantMessage() {
  return (
    <MessagePrimitive.Root style={{ display: "flex", justifyContent: "flex-start" }}>
      <div style={{ maxWidth: "80%", background: "#f5f5f5", borderRadius: 16, padding: "8px 14px" }}>
        <MessagePrimitive.Parts
          components={{
            Text: MarkdownText,
            tools: {
              by_name: {
                launch_research_agent: LaunchResearchAgentCard,
              },
            },
          }}
        />
      </div>
    </MessagePrimitive.Root>
  );
}

function Composer() {
  return (
    <ComposerPrimitive.Root
      style={{
        display: "flex",
        gap: 8,
        border: "1px solid #d9d9d9",
        borderRadius: 8,
        padding: 8,
        background: "#fff",
      }}
    >
      <ComposerPrimitive.Input
        data-testid="chat-input"
        placeholder="Ask a question, or ask me to research a topic…"
        rows={2}
        style={{ flex: 1, resize: "none", border: "none", outline: "none" }}
      />
      <ComposerPrimitive.Send
        data-testid="chat-send"
        style={{
          alignSelf: "flex-end",
          background: "#1677ff",
          color: "#fff",
          border: "none",
          borderRadius: 6,
          padding: "6px 16px",
          cursor: "pointer",
        }}
      >
        Send
      </ComposerPrimitive.Send>
    </ComposerPrimitive.Root>
  );
}

export function ChatView({ user }: { user: SessionUser }) {
  const { runtime, error } = useChatRuntime();

  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <div className="page-shell chat-shell">
        {error && (
          <Alert
            data-testid="chat-error"
            type="error"
            showIcon
            message={error}
            style={{ marginBottom: 16 }}
          />
        )}
        <Card data-testid="chat-card" styles={{ body: { padding: 0 } }}>
          <ThreadPrimitive.Root style={{ display: "flex", flexDirection: "column", height: 480 }}>
            <ThreadPrimitive.Viewport
              data-testid="chat-message-list"
              style={{
                flex: 1,
                overflowY: "auto",
                padding: 16,
                display: "flex",
                flexDirection: "column",
                gap: 12,
              }}
            >
              <AuiIf condition={(s) => s.thread.isEmpty}>
                <Typography.Text type="secondary">
                  Hi {user.display_name} — ask a question, or ask me to research a topic.
                </Typography.Text>
              </AuiIf>
              <ThreadPrimitive.Messages>
                {({ message }) => (message.role === "user" ? <UserMessage /> : <AssistantMessage />)}
              </ThreadPrimitive.Messages>
              <ThreadPrimitive.ViewportFooter style={{ paddingTop: 8 }}>
                <Composer />
              </ThreadPrimitive.ViewportFooter>
            </ThreadPrimitive.Viewport>
          </ThreadPrimitive.Root>
        </Card>
      </div>
    </AssistantRuntimeProvider>
  );
}
