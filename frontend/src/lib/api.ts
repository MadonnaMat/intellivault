import { publicBackendUrl } from "./backend";

export interface ApiResult<T> {
  ok: boolean;
  /** HTTP status, or 0 when the request never completed. */
  status: number;
  data?: T;
  /** A human-readable message when `ok` is false. */
  error?: string;
}

interface RawResponse {
  status: number;
  ok: boolean;
  body: unknown;
  error?: string;
}

/**
 * Fetch + parse JSON without ever throwing. Transport failures come back as
 * `{ status: 0, error }`; a 204 as `{ status: 204, body: undefined }`.
 * Shared by the client (`apiFetch`) and the server (`lib/session.ts`).
 */
export async function requestJson(url: string, init?: RequestInit): Promise<RawResponse> {
  let response: Response;
  try {
    response = await fetch(url, init);
  } catch (error) {
    return {
      status: 0,
      ok: false,
      body: undefined,
      error: error instanceof Error ? error.message : String(error),
    };
  }

  if (response.status === 204) {
    return { status: 204, ok: response.ok, body: undefined };
  }
  try {
    return { status: response.status, ok: response.ok, body: await response.json() };
  } catch {
    return {
      status: response.status,
      ok: false,
      body: undefined,
      error: `Backend responded ${response.status}`,
    };
  }
}

interface ApiOptions {
  /** For endpoints that require a session: on 401, send the user to /login. */
  authed?: boolean;
}

function toResult<T>(raw: RawResponse): ApiResult<T> {
  if (raw.error) return { ok: false, status: raw.status, error: raw.error };
  if (raw.ok) return { ok: true, status: raw.status, data: raw.body as T };
  const detail = (raw.body as { detail?: unknown } | undefined)?.detail;
  return {
    ok: false,
    status: raw.status,
    error: typeof detail === "string" ? detail : `Request failed (${raw.status})`,
  };
}

/**
 * Call a backend JSON endpoint from the browser with the session cookie
 * attached. FastAPI's `{ detail }` string is surfaced as `error`.
 */
export async function apiFetch<T>(
  path: string,
  init?: RequestInit,
  options?: ApiOptions,
): Promise<ApiResult<T>> {
  const raw = await requestJson(`${publicBackendUrl}${path}`, {
    credentials: "include",
    headers: init?.body ? { "content-type": "application/json" } : undefined,
    ...init,
  });

  if (raw.status === 401 && options?.authed && typeof window !== "undefined") {
    window.location.assign("/login");
  }
  return toResult<T>(raw);
}
