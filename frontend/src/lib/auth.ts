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

function passkeyError(error: unknown): string {
  if (error instanceof Error) {
    if (error.name === "NotAllowedError") {
      return "Passkey prompt was dismissed or timed out.";
    }
    return error.message;
  }
  return "The passkey step could not be completed.";
}

export async function registerPasskey(
  email: string,
  displayName: string,
): Promise<ApiResult<SessionUser>> {
  const begin = await apiFetch<PublicKeyCredentialCreationOptionsJSON>(
    "/auth/register/begin",
    { method: "POST", body: JSON.stringify({ email, display_name: displayName }) },
  );
  if (!begin.ok || !begin.data) return { ok: false, error: begin.error };

  try {
    const attestation = await startRegistration({ optionsJSON: begin.data });
    return await apiFetch<SessionUser>("/auth/register/finish", {
      method: "POST",
      body: JSON.stringify(attestation),
    });
  } catch (error) {
    return { ok: false, error: passkeyError(error) };
  }
}

export async function loginPasskey(): Promise<ApiResult<SessionUser>> {
  const begin = await apiFetch<PublicKeyCredentialRequestOptionsJSON>("/auth/login/begin", {
    method: "POST",
    body: JSON.stringify({}),
  });
  if (!begin.ok || !begin.data) return { ok: false, error: begin.error };

  try {
    const assertion = await startAuthentication({ optionsJSON: begin.data });
    return await apiFetch<SessionUser>("/auth/login/finish", {
      method: "POST",
      body: JSON.stringify(assertion),
    });
  } catch (error) {
    return { ok: false, error: passkeyError(error) };
  }
}

export function logout(): Promise<ApiResult<void>> {
  return apiFetch<void>("/auth/logout", { method: "POST" });
}

export function fetchMe(): Promise<ApiResult<SessionUser>> {
  return apiFetch<SessionUser>("/auth/me");
}

export function updateAccount(patch: {
  email?: string;
  displayName?: string;
}): Promise<ApiResult<SessionUser>> {
  return apiFetch<SessionUser>("/auth/me", {
    method: "PATCH",
    body: JSON.stringify({ email: patch.email, display_name: patch.displayName }),
  });
}

export function listCredentials(): Promise<ApiResult<CredentialSummary[]>> {
  return apiFetch<CredentialSummary[]>("/auth/credentials");
}

export async function addPasskey(name: string): Promise<ApiResult<CredentialSummary>> {
  const begin = await apiFetch<PublicKeyCredentialCreationOptionsJSON>(
    "/auth/credentials/begin",
    { method: "POST" },
  );
  if (!begin.ok || !begin.data) return { ok: false, error: begin.error };

  try {
    const attestation = await startRegistration({ optionsJSON: begin.data });
    return await apiFetch<CredentialSummary>("/auth/credentials/finish", {
      method: "POST",
      body: JSON.stringify({ name, credential: attestation }),
    });
  } catch (error) {
    return { ok: false, error: passkeyError(error) };
  }
}

export function removeCredential(id: string): Promise<ApiResult<void>> {
  return apiFetch<void>(`/auth/credentials/${id}`, { method: "DELETE" });
}
