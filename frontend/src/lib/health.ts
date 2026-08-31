import type { components } from "./api-schema";

// Types come straight from the FastAPI OpenAPI schema — regenerate with
// `make gen-api-types` (or `pnpm gen:api`) after changing a backend model.
export type HealthResponse = components["schemas"]["HealthResponse"];
export type ServiceStatus = components["schemas"]["ServiceStatus"];
export type HealthState = HealthResponse["status"];

/** Where the browser reaches the backend (client-side refresh). */
export const publicBackendUrl =
  process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";

/** Where the server component reaches the backend (in-network in compose). */
const serverBackendUrl = process.env.BACKEND_URL ?? publicBackendUrl;

export interface HealthResult {
  /** True when the backend answered with a non-error status. */
  ok: boolean;
  /** Present when the backend answered (any status). */
  data?: HealthResponse;
  /** Present when the request itself failed. */
  error?: string;
}

export async function fetchHealth(baseUrl: string): Promise<HealthResult> {
  try {
    const response = await fetch(`${baseUrl}/health`, { cache: "no-store" });
    const data = (await response.json()) as HealthResponse;
    return { ok: response.ok, data };
  } catch (error) {
    return { ok: false, error: error instanceof Error ? error.message : String(error) };
  }
}

/** Server-side fetch used by the page on first render. */
export function fetchHealthFromServer(): Promise<HealthResult> {
  return fetchHealth(serverBackendUrl);
}
