"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import { Alert, Button, Card, List, Space, Tag, Typography } from "antd";
import type { SessionUser } from "@/lib/auth";
import { reviewRun, streamRun, type AgentRun, type AgentRunStatus } from "@/lib/agent";
import { useAsyncAction } from "@/lib/use-async-action";
import { AppShell } from "../../app-shell";

const STATUS_COLOR: Record<AgentRunStatus, string> = {
  queued: "default",
  running: "processing",
  awaiting_review: "gold",
  succeeded: "green",
  failed: "red",
  cancelled: "default",
};

function PlanCard({ plan }: { plan: NonNullable<AgentRun["plan"]> }) {
  return (
    <Card title="Plan" data-testid="run-plan" style={{ marginBottom: 16 }}>
      <Typography.Paragraph>{plan.summary}</Typography.Paragraph>
      <List size="small" dataSource={plan.queries} renderItem={(query) => <List.Item>{query}</List.Item>} />
    </Card>
  );
}

function ReviewCard({
  pending,
  loading,
  onReview,
}: {
  pending: NonNullable<AgentRun["pending"]>;
  loading: boolean;
  onReview: (decision: "approve" | "reject") => void;
}) {
  return (
    <Card title="Review before committing to your graph" style={{ marginBottom: 16 }}>
      <List
        size="small"
        header="Entities"
        locale={{ emptyText: "No entities drafted" }}
        dataSource={pending.entities ?? []}
        renderItem={(entity) => (
          <List.Item>
            {entity.name} <Typography.Text type="secondary">({entity.kind})</Typography.Text>
          </List.Item>
        )}
      />
      <List
        size="small"
        header="Relationships"
        locale={{ emptyText: "No relationships drafted" }}
        dataSource={pending.relationships ?? []}
        renderItem={(rel) => (
          <List.Item>
            {rel.from_ref} —{rel.kind}→ {rel.to_ref}
          </List.Item>
        )}
      />
      <Space style={{ marginTop: 16 }}>
        <Button
          type="primary"
          data-testid="run-review-approve"
          loading={loading}
          onClick={() => onReview("approve")}
        >
          Approve
        </Button>
        <Button danger data-testid="run-review-reject" loading={loading} onClick={() => onReview("reject")}>
          Reject
        </Button>
      </Space>
    </Card>
  );
}

function ResultCard({ result }: { result: NonNullable<AgentRun["result"]> }) {
  return (
    <Card title="Result" data-testid="run-result" style={{ marginBottom: 16 }}>
      <ReactMarkdown>{result.analysis}</ReactMarkdown>
      {result.skipped && result.skipped.length > 0 && (
        <>
          <Typography.Text strong>Skipped</Typography.Text>
          <List size="small" dataSource={result.skipped} renderItem={(note) => <List.Item>{note}</List.Item>} />
        </>
      )}
    </Card>
  );
}

export function RunDetailView({
  user,
  runId,
  initial,
}: {
  user: SessionUser;
  runId: string;
  initial: AgentRun;
}) {
  const [run, setRun] = useState<AgentRun>(initial);
  const [streamNotice, setStreamNotice] = useState<string | null>(null);
  const { loading, error, run: runAction } = useAsyncAction();
  // The stream treats awaiting_review as terminal (no point holding a
  // connection open through however long a human takes to review), so an
  // approval needs a fresh subscription to keep watching running -> succeeded
  // — bumping this re-runs the effect below.
  const [subscription, setSubscription] = useState(0);

  useEffect(() => {
    let cancelled = false;

    async function subscribe() {
      try {
        for await (const event of streamRun(runId)) {
          if (cancelled) return;
          if (event.event === "status") setRun(event.data as AgentRun);
        }
      } catch {
        if (!cancelled) {
          setStreamNotice("Lost the live connection to this run — refresh to see the latest status.");
        }
      }
    }

    void subscribe();
    return () => {
      cancelled = true;
    };
  }, [runId, subscription]);

  function onReview(decision: "approve" | "reject") {
    return runAction(() => reviewRun(runId, { decision }), {
      fallback: `Could not ${decision} the run`,
      onSuccess: (data) => {
        if (!data) return;
        setRun(data);
        setStreamNotice(null);
        setSubscription((n) => n + 1);
      },
    });
  }

  return (
    <AppShell user={user}>
      <div className="page-shell graph-shell">
        <Space style={{ marginBottom: 16 }}>
          <Link href="/runs" data-testid="back-to-runs">
            Back to runs
          </Link>
        </Space>

        <h1>{run.topic}</h1>
        <Space style={{ marginBottom: 16 }}>
          <Tag data-testid="run-status" color={STATUS_COLOR[run.status]}>
            {run.status}
          </Tag>
          {run.current_node && (
            <Typography.Text data-testid="run-current-node" type="secondary">
              Step: {run.current_node}
            </Typography.Text>
          )}
        </Space>

        {streamNotice && (
          <Alert type="warning" showIcon message={streamNotice} style={{ marginBottom: 16 }} />
        )}
        {error && (
          <Alert data-testid="run-error" type="error" showIcon message={error} style={{ marginBottom: 16 }} />
        )}

        {run.plan && <PlanCard plan={run.plan} />}
        {run.status === "awaiting_review" && run.pending && (
          <ReviewCard pending={run.pending} loading={loading} onReview={onReview} />
        )}
        {run.result && <ResultCard result={run.result} />}
      </div>
    </AppShell>
  );
}
