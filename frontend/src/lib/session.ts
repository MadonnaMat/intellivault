import "server-only";
import { cookies } from "next/headers";
import { serverBackendUrl } from "./backend";
import type { CredentialSummary, SessionUser } from "./auth";

const SESSION_COOKIE = "iv_session";

async function backendGet<T>(path: string): Promise<T | null> {
  const token = (await cookies()).get(SESSION_COOKIE);
  if (!token) return null;
  try {
    const response = await fetch(`${serverBackendUrl}${path}`, {
      headers: { cookie: `${SESSION_COOKIE}=${token.value}` },
      cache: "no-store",
    });
    if (!response.ok) return null;
    return (await response.json()) as T;
  } catch {
    return null;
  }
}

/** The signed-in user from the backend, or null (server components only). */
export function currentUser(): Promise<SessionUser | null> {
  return backendGet<SessionUser>("/auth/me");
}

export function currentUserCredentials(): Promise<CredentialSummary[] | null> {
  return backendGet<CredentialSummary[]>("/auth/credentials");
}
