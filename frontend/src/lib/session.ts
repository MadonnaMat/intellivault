import "server-only";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { requestJson } from "./api";
import { SESSION_COOKIE, serverBackendUrl } from "./backend";
import type { CredentialSummary, SessionUser } from "./auth";
import type { GraphView } from "./graph";

/**
 * GET a backend endpoint from a server component, forwarding the session cookie.
 * Returns null only when the backend says "not authenticated" (401); a transport
 * error or 5xx throws, so a transient backend problem shows an error page rather
 * than silently logging the user out.
 */
async function backendGet<T>(path: string): Promise<T | null> {
  const token = (await cookies()).get(SESSION_COOKIE);
  if (!token) return null;

  const raw = await requestJson(`${serverBackendUrl}${path}`, {
    headers: { cookie: `${SESSION_COOKIE}=${token.value}` },
    cache: "no-store",
  });

  if (raw.status === 401) return null;
  if (!raw.ok) {
    throw new Error(raw.error ?? `Backend responded ${raw.status} for ${path}`);
  }
  return raw.body as T;
}

/** The signed-in user, or null (server components only). Throws on backend error. */
export function currentUser(): Promise<SessionUser | null> {
  return backendGet<SessionUser>("/auth/me");
}

export function currentUserCredentials(): Promise<CredentialSummary[] | null> {
  return backendGet<CredentialSummary[]>("/auth/credentials");
}

/** The caller's visible slice of the knowledge graph (server components only). */
export function currentGraph(): Promise<GraphView | null> {
  return backendGet<GraphView>("/graph");
}

/** For the public auth pages: bounce to `/` once a real session is confirmed. */
export async function redirectIfAuthenticated(): Promise<void> {
  if (await currentUser()) redirect("/");
}
