import type { components } from "./api-schema";
import { requestJson } from "./api";
import { publicBackendUrl, serverBackendUrl } from "./backend";

// Types come straight from the FastAPI OpenAPI schema — regenerate with
// `make gen-api-types` (or `pnpm gen:api`) after changing a backend model.
export type HealthResponse = components["schemas"]["HealthResponse"];
export type ServiceStatus = components["schemas"]["ServiceStatus"];
export type HealthState = HealthResponse["status"];

export { publicBackendUrl };

export interface HealthResult {
  /** True when the backend answered with a non-error status. */
  ok: boolean;
  /** Present when the backend answered (any status). */
  data?: HealthResponse;
  /** Present when the request itself failed. */
  error?: string;
}

export async function fetchHealth(baseUrl: string): Promise<HealthResult> {
  const raw = await requestJson(`${baseUrl}/health`, { cache: "no-store" });
  if (raw.status === 0) return { ok: false, error: raw.error };
  if (raw.body === undefined) {
    // Reachable but the body isn't the health JSON (proxy error page, 502/504).
    return { ok: false, error: `Backend responded ${raw.status} with a non-JSON body` };
  }
  return { ok: raw.ok, data: raw.body as HealthResponse };
}

/** Server-side fetch used by the page on first render. */
export function fetchHealthFromServer(): Promise<HealthResult> {
  return fetchHealth(serverBackendUrl);
}
