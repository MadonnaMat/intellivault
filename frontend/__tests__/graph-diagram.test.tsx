import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { GraphEntity, GraphRelationship } from "@/lib/graph";

const { cy, cytoscape } = vi.hoisted(() => {
  const cy = { on: vi.fn(), destroy: vi.fn() };
  return { cy, cytoscape: vi.fn(() => cy) };
});
vi.mock("cytoscape", () => ({ default: cytoscape }));

import { GraphDiagram } from "@/app/graph/graph-diagram";

function entity(overrides: Partial<GraphEntity>): GraphEntity {
  return {
    id: "e",
    owner_id: "u1",
    visibility: "private",
    name: "E",
    kind: "n",
    attributes: {},
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

interface FakeTapEvent {
  target: { data: (key: string) => unknown; id: () => string };
  originalEvent?: { shiftKey?: boolean };
}

afterEach(() => {
  cleanup();
  cytoscape.mockClear();
  cy.on.mockClear();
});

describe("GraphDiagram", () => {
  it("shows a hint and never boots cytoscape when there is nothing to draw", () => {
    render(<GraphDiagram entities={[]} relationships={[]} ownerId="u1" onToggle={vi.fn()} />);
    expect(screen.getByTestId("graph-empty")).toBeInTheDocument();
    expect(cytoscape).not.toHaveBeenCalled();
  });

  it("feeds nodes + edges to cytoscape and toggles only your own nodes on tap", () => {
    const onToggle = vi.fn();
    const mine = entity({ id: "a", owner_id: "u1" });
    const theirs = entity({ id: "b", owner_id: "u2", visibility: "public" });
    const rel: GraphRelationship = {
      id: "r",
      owner_id: "u1",
      from_id: "a",
      to_id: "b",
      kind: "k",
      visibility: "private",
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    };

    render(
      <GraphDiagram
        entities={[mine, theirs]}
        relationships={[rel]}
        ownerId="u1"
        onToggle={onToggle}
      />,
    );

    const [options] = cytoscape.mock.calls[0] as unknown as [{ elements: unknown[] }];
    expect(options.elements).toHaveLength(3);

    const tap = cy.on.mock.calls.find((call) => call[0] === "tap" && call[1] === "node");
    const handler = tap?.[2] as (event: FakeTapEvent) => void;

    handler({ target: { data: (key) => (key === "mine" ? "yes" : undefined), id: () => "a" } });
    expect(onToggle).toHaveBeenCalledWith(mine, false);

    handler({ target: { data: () => "no", id: () => "b" } });
    expect(onToggle).toHaveBeenCalledTimes(1);
  });

  it("cascades on shift-tap, but not on a plain tap", () => {
    const onToggle = vi.fn();
    const mine = entity({ id: "a", owner_id: "u1" });

    render(<GraphDiagram entities={[mine]} relationships={[]} ownerId="u1" onToggle={onToggle} />);

    const tap = cy.on.mock.calls.find((call) => call[0] === "tap" && call[1] === "node");
    const handler = tap?.[2] as (event: FakeTapEvent) => void;
    const target = { data: (key: string) => (key === "mine" ? "yes" : undefined), id: () => "a" };

    handler({ target, originalEvent: { shiftKey: true } });
    expect(onToggle).toHaveBeenNthCalledWith(1, mine, true);

    handler({ target, originalEvent: { shiftKey: false } });
    expect(onToggle).toHaveBeenNthCalledWith(2, mine, false);

    handler({ target });
    expect(onToggle).toHaveBeenNthCalledWith(3, mine, false);
  });
});
