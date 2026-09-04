import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { AgentRunSummary } from "@/lib/agent";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
  usePathname: () => "/runs",
}));

import { RunsListView } from "@/app/runs/runs-list-view";

const user = { id: "u1", email: "ada@example.com", display_name: "Ada" };

function run(overrides: Partial<AgentRunSummary> = {}): AgentRunSummary {
  return {
    id: "r1",
    topic: "the history of the transistor",
    status: "running",
    created_at: "2026-09-04T00:00:00Z",
    updated_at: "2026-09-04T00:01:00Z",
    ...overrides,
  };
}

afterEach(() => cleanup());

describe("RunsListView", () => {
  it("lists each run's topic, status and a link to its detail page", () => {
    render(<RunsListView user={user} runs={[run()]} />);

    expect(screen.getByTestId("runs-table")).toBeInTheDocument();
    expect(screen.getByTestId("run-row-r1")).toBeInTheDocument();
    const link = screen.getByRole("link", { name: "the history of the transistor" });
    expect(link).toHaveAttribute("href", "/runs/r1");
    expect(screen.getByText("running")).toBeInTheDocument();
  });

  it("shows an empty-state message when there are no runs", () => {
    render(<RunsListView user={user} runs={[]} />);
    expect(screen.getByText(/no runs yet/i)).toBeInTheDocument();
  });
});
