"use client";

import Link from "next/link";
import { Card, Table, Tag } from "antd";
import type { SessionUser } from "@/lib/auth";
import type { AgentRunStatus, AgentRunSummary } from "@/lib/agent";
import { AppShell } from "../app-shell";

const STATUS_COLOR: Record<AgentRunStatus, string> = {
  queued: "default",
  running: "processing",
  awaiting_review: "gold",
  succeeded: "green",
  failed: "red",
  cancelled: "default",
};

const columns = [
  {
    title: "Topic",
    key: "topic",
    render: (_: unknown, run: AgentRunSummary) => <Link href={`/runs/${run.id}`}>{run.topic}</Link>,
  },
  {
    title: "Status",
    key: "status",
    render: (_: unknown, run: AgentRunSummary) => (
      <Tag color={STATUS_COLOR[run.status]}>{run.status}</Tag>
    ),
  },
  {
    title: "Created",
    key: "created_at",
    render: (_: unknown, run: AgentRunSummary) => new Date(run.created_at).toLocaleString(),
  },
  {
    title: "Updated",
    key: "updated_at",
    render: (_: unknown, run: AgentRunSummary) => new Date(run.updated_at).toLocaleString(),
  },
];

export function RunsListView({ user, runs }: { user: SessionUser; runs: AgentRunSummary[] }) {
  return (
    <AppShell user={user}>
      <div className="page-shell graph-shell">
        <h1>Agent Runs</h1>
        <Card>
          <Table
            data-testid="runs-table"
            rowKey="id"
            size="small"
            dataSource={runs}
            columns={columns}
            pagination={false}
            locale={{ emptyText: "No runs yet — start one from Chat." }}
            onRow={(run) => ({ "data-testid": `run-row-${run.id}` }) as object}
          />
        </Card>
      </div>
    </AppShell>
  );
}
