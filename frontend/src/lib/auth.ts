import {
  startAuthentication,
  startRegistration,
  type PublicKeyCredentialCreationOptionsJSON,
  type PublicKeyCredentialRequestOptionsJSON,
} from "@simplewebauthn/browser";
import type { components } from "./api-schema";
import { apiFetch, type ApiResult } from "./api";

// Regenerate with `make gen-api-types` after changing a backend model.
export type SessionUser = components["schemas"]["SessionUser"];
export type CredentialSummary = components["schemas"]["CredentialSummary"];

// Endpoints that need a live session — a 401 here means "sign back in".
const AUTHED = { authed: true } as const;

function passkeyError(error: unknown): string {
  if (error instanceof Error) {
    if (error.name === "NotAllowedError") {
      return "Passkey prompt was dismissed or timed out.";
    }
    return error.message;
  }
  return "The passkey step could not be completed.";
}

/**
 * The shared begin -> browser ceremony -> finish shape. `browserStep` is
 * `startRegistration` or `startAuthentication`; its thrown errors are mapped to
 * a friendly string.
 */
async function runCeremony<O, T>(
  begin: { path: string; body?: unknown },
  browserStep: (opts: { optionsJSON: O }) => Promise<unknown>,
  finish: (ceremonyResponse: unknown) => { path: string; body: unknown },
): Promise<ApiResult<T>> {
  const options = await apiFetch<O>(begin.path, {
    method: "POST",
    body: begin.body === undefined ? undefined : JSON.stringify(begin.body),
  });
  if (!options.ok || !options.data) {
    return { ok: false, status: options.status, error: options.error };
  }

  let ceremonyResponse: unknown;
  try {
    ceremonyResponse = await browserStep({ optionsJSON: options.data });
  } catch (error) {
    return { ok: false, status: 0, error: passkeyError(error) };
  }

  const { path, body } = finish(ceremonyResponse);
  return apiFetch<T>(path, { method: "POST", body: JSON.stringify(body) });
}

export function registerPasskey(
  email: string,
  displayName: string,
): Promise<ApiResult<SessionUser>> {
  return runCeremony<PublicKeyCredentialCreationOptionsJSON, SessionUser>(
    { path: "/auth/register/begin", body: { email, display_name: displayName } },
    startRegistration,
    (attestation) => ({ path: "/auth/register/finish", body: attestation }),
  );
}

export function loginPasskey(): Promise<ApiResult<SessionUser>> {
  return runCeremony<PublicKeyCredentialRequestOptionsJSON, SessionUser>(
    { path: "/auth/login/begin" },
    startAuthentication,
    (assertion) => ({ path: "/auth/login/finish", body: assertion }),
  );
}

export function addPasskey(name: string): Promise<ApiResult<CredentialSummary>> {
  return runCeremony<PublicKeyCredentialCreationOptionsJSON, CredentialSummary>(
    { path: "/auth/credentials/begin" },
    startRegistration,
    (attestation) => ({
      path: "/auth/credentials/finish",
      body: { name, credential: attestation },
    }),
  );
}

export function logout(): Promise<ApiResult<void>> {
  return apiFetch<void>("/auth/logout", { method: "POST" });
}

export function fetchMe(): Promise<ApiResult<SessionUser>> {
  return apiFetch<SessionUser>("/auth/me", undefined, AUTHED);
}

export function updateAccount(patch: {
  email?: string;
  displayName?: string;
}): Promise<ApiResult<SessionUser>> {
  return apiFetch<SessionUser>(
    "/auth/me",
    {
      method: "PATCH",
      body: JSON.stringify({ email: patch.email, display_name: patch.displayName }),
    },
    AUTHED,
  );
}

export function listCredentials(): Promise<ApiResult<CredentialSummary[]>> {
  return apiFetch<CredentialSummary[]>("/auth/credentials", undefined, AUTHED);
}

export function removeCredential(id: string): Promise<ApiResult<void>> {
  return apiFetch<void>(`/auth/credentials/${id}`, { method: "DELETE" }, AUTHED);
}
