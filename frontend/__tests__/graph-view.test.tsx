import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { GraphEntity } from "@/lib/graph";

const {
  refresh,
  createEntity,
  createRelationship,
  setEntityVisibility,
  seedSampleGraph,
  deleteEntity,
  deleteRelationship,
} = vi.hoisted(() => ({
  refresh: vi.fn(),
  createEntity: vi.fn(),
  createRelationship: vi.fn(),
  setEntityVisibility: vi.fn(),
  seedSampleGraph: vi.fn(),
  deleteEntity: vi.fn(),
  deleteRelationship: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh }),
  usePathname: () => "/graph",
}));
vi.mock("@/lib/graph", () => ({
  createEntity,
  createRelationship,
  setEntityVisibility,
  seedSampleGraph,
  deleteEntity,
  deleteRelationship,
}));
vi.mock("@/app/graph/graph-diagram", () => ({
  GraphDiagram: ({
    entities,
    onToggle,
  }: {
    entities: GraphEntity[];
    onToggle: (entity: GraphEntity) => void;
  }) => (
    <div data-testid="graph-diagram">
      {entities.map((entity) => (
        <button
          key={entity.id}
          data-testid={`diagram-node-${entity.id}`}
          onClick={() => onToggle(entity)}
        >
          {entity.name}
        </button>
      ))}
    </div>
  ),
}));

import { GraphView } from "@/app/graph/graph-view";

const user = { id: "u1", email: "ada@example.com", display_name: "Ada" };

function entity(overrides: Partial<GraphEntity> = {}): GraphEntity {
  return {
    id: "e1",
    owner_id: "u1",
    visibility: "private",
    name: "Acme",
    kind: "org",
    attributes: {},
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

const empty = { entities: [], relationships: [] };

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("GraphView", () => {
  it("tags entities by visibility and ownership", () => {
    render(
      <GraphView
        user={user}
        initial={{
          entities: [
            entity(),
            entity({ id: "e2", name: "Shared", owner_id: "u2", visibility: "public" }),
          ],
          relationships: [],
        }}
      />,
    );
    const mineRow = screen.getByTestId("entity-row-e1");
    expect(mineRow).toHaveTextContent("private");
    expect(mineRow).toHaveTextContent("you");
    const sharedRow = screen.getByTestId("entity-row-e2");
    expect(sharedRow).toHaveTextContent("public");
    expect(sharedRow).toHaveTextContent("shared");
  });

  it("only offers the visibility switch on entities you own", () => {
    render(
      <GraphView
        user={user}
        initial={{
          entities: [entity({ id: "e2", owner_id: "u2", visibility: "public" })],
          relationships: [],
        }}
      />,
    );
    expect(screen.queryByTestId("entity-e2-visibility")).not.toBeInTheDocument();
  });

  it("flips visibility without cascade by default", async () => {
    setEntityVisibility.mockResolvedValue({ ok: true, data: { affected_ids: ["e1"] } });
    render(<GraphView user={user} initial={{ entities: [entity()], relationships: [] }} />);

    fireEvent.click(screen.getByTestId("entity-e1-visibility"));

    await waitFor(() =>
      expect(setEntityVisibility).toHaveBeenCalledWith("e1", {
        visibility: "public",
        cascade: false,
      }),
    );
  });

  it("cascades when the row checkbox is ticked", async () => {
    setEntityVisibility.mockResolvedValue({ ok: true, data: { affected_ids: ["e1"] } });
    render(<GraphView user={user} initial={{ entities: [entity()], relationships: [] }} />);

    fireEvent.click(screen.getByTestId("entity-e1-cascade"));
    fireEvent.click(screen.getByTestId("entity-e1-visibility"));

    await waitFor(() =>
      expect(setEntityVisibility).toHaveBeenCalledWith("e1", {
        visibility: "public",
        cascade: true,
      }),
    );
  });

  it("toggles from a diagram node too", async () => {
    setEntityVisibility.mockResolvedValue({ ok: true, data: { affected_ids: ["e1"] } });
    render(<GraphView user={user} initial={{ entities: [entity()], relationships: [] }} />);

    fireEvent.click(screen.getByTestId("diagram-node-e1"));

    await waitFor(() => expect(setEntityVisibility).toHaveBeenCalledWith("e1", expect.anything()));
  });

  it("creates an entity through the form", async () => {
    createEntity.mockResolvedValue({ ok: true, data: entity() });
    render(<GraphView user={user} initial={empty} />);

    fireEvent.change(screen.getByTestId("create-entity-name"), { target: { value: "Beta" } });
    fireEvent.change(screen.getByTestId("create-entity-kind"), { target: { value: "project" } });
    fireEvent.click(screen.getByTestId("create-entity-submit"));

    await waitFor(() =>
      expect(createEntity).toHaveBeenCalledWith({
        name: "Beta",
        kind: "project",
        visibility: "private",
        attributes: {},
      }),
    );
  });

  it("loads the sample graph, but only when the graph is empty", async () => {
    seedSampleGraph.mockResolvedValue({ ok: true, status: 200 });
    const { rerender } = render(<GraphView user={user} initial={empty} />);

    fireEvent.click(screen.getByTestId("load-sample-graph"));
    await waitFor(() => expect(seedSampleGraph).toHaveBeenCalled());

    rerender(<GraphView user={user} initial={{ entities: [entity()], relationships: [] }} />);
    expect(screen.getByTestId("load-sample-graph")).toBeDisabled();
  });

  it("deletes an entity you own", async () => {
    deleteEntity.mockResolvedValue({ ok: true });
    render(<GraphView user={user} initial={{ entities: [entity()], relationships: [] }} />);

    fireEvent.click(screen.getByTestId("entity-e1-delete"));
    // the Popconfirm's confirm button is the second "Delete" to appear
    const confirm = await screen.findAllByRole("button", { name: "Delete" });
    fireEvent.click(confirm[confirm.length - 1]);

    await waitFor(() => expect(deleteEntity).toHaveBeenCalledWith("e1"));
  });

  it("surfaces a backend error", async () => {
    seedSampleGraph.mockResolvedValue({ ok: false, error: "Neo4j is down" });
    render(<GraphView user={user} initial={empty} />);

    fireEvent.click(screen.getByTestId("load-sample-graph"));

    expect(await screen.findByTestId("graph-error")).toHaveTextContent("Neo4j is down");
  });
});
