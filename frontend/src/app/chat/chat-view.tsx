"use client";

import { Button, Card, Input, Typography } from "antd";
import type { SessionUser } from "@/lib/auth";

// Wired to the real chat backend in a later slice (AssistantTransport via
// @assistant-ui/react) — this is the static layout shell for now.
export function ChatView({ user }: { user: SessionUser }) {
  return (
    <main style={{ maxWidth: 760, margin: "0 auto", padding: "2rem 1.25rem" }}>
      <Card data-testid="chat-card">
        <div data-testid="chat-message-list" style={{ minHeight: 320 }}>
          <Typography.Text type="secondary">
            Hi {user.display_name} — chat isn&apos;t wired up yet. Ask a question or
            start a research request once it lands.
          </Typography.Text>
        </div>
        <Input.TextArea
          data-testid="chat-input"
          placeholder="Ask a question, or ask me to research a topic…"
          autoSize={{ minRows: 2, maxRows: 6 }}
          disabled
          style={{ marginTop: 16 }}
        />
        <Button type="primary" data-testid="chat-send" disabled style={{ marginTop: 8 }}>
          Send
        </Button>
      </Card>
    </main>
  );
}
