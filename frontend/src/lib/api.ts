import { publicBackendUrl } from "./backend";

export interface ApiResult<T> {
  ok: boolean;
  data?: T;
  /** A human-readable message when `ok` is false. */
  error?: string;
}

/**
 * Fetch a backend JSON endpoint with the session cookie attached.
 *
 * Never throws: transport failures, non-JSON bodies and error statuses all come
 * back as `{ ok: false, error }`. A 204 returns `{ ok: true }` with no data.
 * FastAPI's `{ detail }` string is surfaced as `error` when present.
 */
export async function apiFetch<T>(path: string, init?: RequestInit): Promise<ApiResult<T>> {
  let response: Response;
  try {
    response = await fetch(`${publicBackendUrl}${path}`, {
      credentials: "include",
      headers: init?.body ? { "content-type": "application/json" } : undefined,
      ...init,
    });
  } catch (error) {
    return { ok: false, error: error instanceof Error ? error.message : String(error) };
  }

  if (response.status === 204) return { ok: response.ok };

  let body: unknown;
  try {
    body = await response.json();
  } catch {
    return { ok: false, error: `Backend responded ${response.status}` };
  }

  if (!response.ok) {
    const detail = (body as { detail?: unknown }).detail;
    return {
      ok: false,
      error: typeof detail === "string" ? detail : `Request failed (${response.status})`,
    };
  }
  return { ok: true, data: body as T };
}
