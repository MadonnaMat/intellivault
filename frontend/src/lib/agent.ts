import type { components } from "./api-schema";
import { apiFetch, type ApiResult } from "./api";
import { publicBackendUrl } from "./backend";
import { parseSse, type SseEvent } from "./sse";

// Regenerate with `make gen-api-types` after changing a backend model.
export type AgentRun = components["schemas"]["AgentRun"];
export type AgentRunSummary = components["schemas"]["AgentRunSummary"];
export type AgentRunReview = components["schemas"]["AgentRunReview"];
export type AgentRunStatus = AgentRun["status"];
export type DraftEntity = components["schemas"]["DraftEntity"];
export type DraftRelationship = components["schemas"]["DraftRelationship"];

const AUTHED = { authed: true } as const;

export function listRuns(): Promise<ApiResult<AgentRunSummary[]>> {
  return apiFetch<AgentRunSummary[]>("/agent/runs", undefined, AUTHED);
}

export function getRun(id: string): Promise<ApiResult<AgentRun>> {
  return apiFetch<AgentRun>(`/agent/runs/${id}`, undefined, AUTHED);
}

export function reviewRun(id: string, review: AgentRunReview): Promise<ApiResult<AgentRun>> {
  return apiFetch<AgentRun>(
    `/agent/runs/${id}/review`,
    { method: "POST", body: JSON.stringify(review) },
    AUTHED,
  );
}

/**
 * Live status for one run. A plain authenticated `fetch` — unlike the chat
 * transport, we build this request ourselves, so `credentials: "include"`
 * is all that's needed to carry the session cookie cross-origin; no proxy
 * route required.
 */
export async function* streamRun(id: string): AsyncGenerator<SseEvent> {
  const response = await fetch(`${publicBackendUrl}/agent/runs/${id}/stream`, {
    credentials: "include",
  });
  yield* parseSse(response);
}
