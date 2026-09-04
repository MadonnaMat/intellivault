import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { AgentRun } from "@/lib/agent";

const { reviewRun, streamRunMock } = vi.hoisted(() => ({
  reviewRun: vi.fn(),
  streamRunMock: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
  usePathname: () => "/runs/r1",
}));
vi.mock("@/lib/agent", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/agent")>();
  return { ...actual, reviewRun, streamRun: streamRunMock };
});

import { RunDetailView } from "@/app/runs/[id]/run-detail-view";

const user = { id: "u1", email: "ada@example.com", display_name: "Ada" };

function makeRun(overrides: Partial<AgentRun> = {}): AgentRun {
  return {
    id: "r1",
    topic: "the transistor",
    status: "running",
    created_at: "2026-09-04T00:00:00Z",
    updated_at: "2026-09-04T00:01:00Z",
    committed_entity_ids: [],
    committed_relationship_ids: [],
    ...overrides,
  };
}

async function* noEvents() {
  /* never yields — the default for tests that don't care about live updates */
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("RunDetailView", () => {
  it("renders status and current node", () => {
    streamRunMock.mockImplementation(noEvents);
    render(<RunDetailView user={user} runId="r1" initial={makeRun({ current_node: "search" })} />);

    expect(screen.getByTestId("run-status")).toHaveTextContent("running");
    expect(screen.getByTestId("run-current-node")).toHaveTextContent("search");
  });

  it("renders the plan when present", () => {
    streamRunMock.mockImplementation(noEvents);
    render(
      <RunDetailView
        user={user}
        runId="r1"
        initial={makeRun({ plan: { summary: "Look into it", queries: ["q1"] } })}
      />,
    );

    expect(screen.getByTestId("run-plan")).toHaveTextContent("Look into it");
    expect(screen.getByTestId("run-plan")).toHaveTextContent("q1");
  });

  it("renders the result as markdown", () => {
    streamRunMock.mockImplementation(noEvents);
    render(
      <RunDetailView
        user={user}
        runId="r1"
        initial={makeRun({
          status: "succeeded",
          result: { analysis: "**done**", entities_created: 1, relationships_created: 0, skipped: [] },
        })}
      />,
    );

    expect(screen.getByTestId("run-result").querySelector("strong")).toHaveTextContent("done");
  });

  it("shows review controls when awaiting_review and approves via reviewRun", async () => {
    streamRunMock.mockImplementation(noEvents);
    reviewRun.mockResolvedValue({ ok: true, data: makeRun({ status: "running" }) });
    render(
      <RunDetailView
        user={user}
        runId="r1"
        initial={makeRun({
          status: "awaiting_review",
          pending: { entities: [{ temp_id: "e1", name: "Bell Labs", kind: "org" }], relationships: [] },
        })}
      />,
    );

    expect(screen.getByTestId("run-review-approve")).toBeInTheDocument();
    expect(streamRunMock).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByTestId("run-review-approve"));

    await waitFor(() => expect(reviewRun).toHaveBeenCalledWith("r1", { decision: "approve" }));
    await waitFor(() => expect(screen.getByTestId("run-status")).toHaveTextContent("running"));
    // awaiting_review is terminal for the stream (it closed once the initial
    // subscription reported it) — approving must open a fresh one so later
    // running -> succeeded progress is still observed live.
    await waitFor(() => expect(streamRunMock).toHaveBeenCalledTimes(2));
  });

  it("rejects via reviewRun on the reject button", async () => {
    streamRunMock.mockImplementation(noEvents);
    reviewRun.mockResolvedValue({ ok: true, data: makeRun({ status: "cancelled" }) });
    render(
      <RunDetailView
        user={user}
        runId="r1"
        initial={makeRun({ status: "awaiting_review", pending: { entities: [], relationships: [] } })}
      />,
    );

    fireEvent.click(screen.getByTestId("run-review-reject"));
    await waitFor(() => expect(reviewRun).toHaveBeenCalledWith("r1", { decision: "reject" }));
  });

  it("updates status from a live streamRun event", async () => {
    async function* events() {
      yield { event: "status", data: makeRun({ status: "succeeded" }) };
    }
    streamRunMock.mockImplementation(events);
    render(<RunDetailView user={user} runId="r1" initial={makeRun({ status: "running" })} />);

    await waitFor(() => expect(screen.getByTestId("run-status")).toHaveTextContent("succeeded"));
  });
});
