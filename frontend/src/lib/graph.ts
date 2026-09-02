import type { components } from "./api-schema";
import { apiFetch, type ApiResult } from "./api";

// Regenerate with `make gen-api-types` after changing a backend model.
export type GraphEntity = components["schemas"]["Entity"];
export type GraphRelationship = components["schemas"]["Relationship"];
export type GraphView = components["schemas"]["GraphView"];
export type EntityInput = components["schemas"]["EntityInput"];
export type RelationshipInput = components["schemas"]["RelationshipInput"];
export type VisibilityChange = components["schemas"]["VisibilityChange"];
export type VisibilityChangeResult = components["schemas"]["VisibilityChangeResult"];
// `Visibility` is a bare Literal on the backend, so it isn't emitted as a named
// schema — derive it from a field that uses it.
export type Visibility = GraphEntity["visibility"];

const AUTHED = { authed: true } as const;

export function createEntity(input: EntityInput): Promise<ApiResult<GraphEntity>> {
  return apiFetch<GraphEntity>(
    "/graph/entities",
    { method: "POST", body: JSON.stringify(input) },
    AUTHED,
  );
}

export function createRelationship(
  input: RelationshipInput,
): Promise<ApiResult<GraphRelationship>> {
  return apiFetch<GraphRelationship>(
    "/graph/relationships",
    { method: "POST", body: JSON.stringify(input) },
    AUTHED,
  );
}

export function setEntityVisibility(
  id: string,
  change: VisibilityChange,
): Promise<ApiResult<VisibilityChangeResult>> {
  return apiFetch<VisibilityChangeResult>(
    `/graph/entities/${id}/visibility`,
    { method: "PATCH", body: JSON.stringify(change) },
    AUTHED,
  );
}

export function deleteEntity(id: string): Promise<ApiResult<void>> {
  return apiFetch<void>(`/graph/entities/${id}`, { method: "DELETE" }, AUTHED);
}

export function deleteRelationship(id: string): Promise<ApiResult<void>> {
  return apiFetch<void>(`/graph/relationships/${id}`, { method: "DELETE" }, AUTHED);
}

/** A tiny fixed graph, injected one real API call at a time — a "does it work?" button. */
const SAMPLE_ENTITIES: EntityInput[] = [
  { name: "Acme Corp", kind: "organization", visibility: "public", attributes: {} },
  { name: "Project Atlas", kind: "project", visibility: "private", attributes: {} },
  { name: "Jane Doe", kind: "person", visibility: "private", attributes: {} },
  { name: "OpenAI", kind: "organization", visibility: "public", attributes: {} },
  { name: "GPT-4", kind: "model", visibility: "public", attributes: {} },
];

// [fromIndex, toIndex, kind, visibility]
const SAMPLE_LINKS: [number, number, string, Visibility][] = [
  [0, 1, "sponsors", "private"],
  [2, 1, "works_on", "private"],
  [0, 2, "employs", "private"],
  [3, 4, "develops", "public"],
  [1, 4, "uses", "private"],
];

export async function seedSampleGraph(): Promise<ApiResult<unknown>> {
  const ids: string[] = [];
  for (const entity of SAMPLE_ENTITIES) {
    const result = await createEntity(entity);
    if (!result.ok || !result.data) return result;
    ids.push(result.data.id);
  }
  for (const [from, to, kind, visibility] of SAMPLE_LINKS) {
    const result = await createRelationship({
      from_id: ids[from],
      to_id: ids[to],
      kind,
      visibility,
    });
    if (!result.ok) return result;
  }
  return { ok: true, status: 200 };
}
