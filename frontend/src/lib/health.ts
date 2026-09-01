import type { components } from "./api-schema";
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
  let response: Response;
  try {
    response = await fetch(`${baseUrl}/health`, { cache: "no-store" });
  } catch (error) {
    return { ok: false, error: error instanceof Error ? error.message : String(error) };
  }

  try {
    const data = (await response.json()) as HealthResponse;
    return { ok: response.ok, data };
  } catch {
    // Reachable but the body isn't the health JSON (proxy error page, 502/504).
    return { ok: false, error: `Backend responded ${response.status} with a non-JSON body` };
  }
}

/** Server-side fetch used by the page on first render. */
export function fetchHealthFromServer(): Promise<HealthResult> {
  return fetchHealth(serverBackendUrl);
}
