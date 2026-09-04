"use client";

import { useEffect, useRef } from "react";
import cytoscape from "cytoscape";
import type { GraphEntity, GraphRelationship } from "@/lib/graph";

const ACCENT = "#1677ff";

function toElements(
  entities: GraphEntity[],
  relationships: GraphRelationship[],
  ownerId: string,
): cytoscape.ElementDefinition[] {
  const present = new Set(entities.map((entity) => entity.id));
  const nodes: cytoscape.ElementDefinition[] = entities.map((entity) => ({
    data: {
      id: entity.id,
      label: entity.name,
      visibility: entity.visibility,
      mine: entity.owner_id === ownerId ? "yes" : "no",
    },
  }));
  const edges: cytoscape.ElementDefinition[] = relationships
    .filter((rel) => present.has(rel.from_id) && present.has(rel.to_id))
    .map((rel) => ({
      data: {
        id: rel.id,
        source: rel.from_id,
        target: rel.to_id,
        label: rel.kind,
        visibility: rel.visibility,
      },
    }));
  return [...nodes, ...edges];
}

const STYLESHEET: cytoscape.StylesheetJson = [
  {
    selector: "node",
    style: {
      label: "data(label)",
      "font-size": 11,
      color: "#8c8c8c",
      "text-valign": "top",
      "text-margin-y": -2,
      "background-color": "#ffffff",
      "border-color": ACCENT,
      "border-width": 2,
      width: 18,
      height: 18,
    },
  },
  { selector: 'node[visibility = "public"]', style: { "background-color": ACCENT } },
  { selector: 'node[mine = "yes"]', style: { "border-width": 4 } },
  {
    selector: "edge",
    style: {
      width: 1.5,
      "line-color": "#8c8c8c",
      "target-arrow-color": "#8c8c8c",
      "target-arrow-shape": "triangle",
      "curve-style": "bezier",
      label: "data(label)",
      "font-size": 9,
      color: "#aaaaaa",
    },
  },
  { selector: 'edge[visibility = "private"]', style: { "line-style": "dashed" } },
];

/**
 * Interactive node-link view of the visible graph (Cytoscape.js): pan, zoom,
 * drag nodes; filled dot = public, hollow = private; dashed edge = private;
 * thick ring = yours. Tapping a node you own toggles its visibility;
 * shift-tapping cascades the toggle to its connected owned sub-graph.
 */
export function GraphDiagram({
  entities,
  relationships,
  ownerId,
  onToggle,
}: {
  entities: GraphEntity[];
  relationships: GraphRelationship[];
  ownerId: string;
  onToggle: (entity: GraphEntity, cascade: boolean) => void;
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const onToggleRef = useRef(onToggle);
  onToggleRef.current = onToggle;

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const cy = cytoscape({
      container,
      elements: toElements(entities, relationships, ownerId),
      style: STYLESHEET,
      layout: { name: "cose", animate: false, padding: 24 },
      minZoom: 0.3,
      maxZoom: 2.5,
    });

    cy.on("tap", "node", (event: cytoscape.EventObject) => {
      if (event.target.data("mine") !== "yes") return;
      const entity = entities.find((candidate) => candidate.id === event.target.id());
      if (!entity) return;
      const original = event.originalEvent as MouseEvent | undefined;
      onToggleRef.current(entity, !!original?.shiftKey);
    });

    return () => cy.destroy();
  }, [entities, relationships, ownerId]);

  if (entities.length === 0) {
    return (
      <p data-testid="graph-empty">
        Nothing here yet — create an entity or load the sample graph.
      </p>
    );
  }

  return (
    <>
      <div
        ref={containerRef}
        data-testid="graph-diagram"
        style={{
          width: "100%",
          height: 380,
          border: "1px solid #f0f0f0",
          borderRadius: 6,
        }}
      />
      <p style={{ color: "#8c8c8c", fontSize: 12, marginTop: 8, marginBottom: 0 }}>
        Click to toggle visibility · Shift-click to toggle the connected sub-graph
      </p>
    </>
  );
}
