import { cookies } from "next/headers";
import { SESSION_COOKIE, serverBackendUrl } from "@/lib/backend";

/**
 * Same-origin proxy for POST /chat. `useAssistantTransportRuntime`'s internal
 * fetch sets no `credentials` option, so a direct browser -> backend call
 * would silently drop the HttpOnly session cookie on this app's cross-origin
 * frontend/backend split. Browser -> this route is same-origin (the cookie
 * rides along automatically); only this hop forwards it explicitly, the same
 * way `lib/session.ts`'s `backendGet` does for server components.
 */
export async function POST(request: Request): Promise<Response> {
  const token = (await cookies()).get(SESSION_COOKIE);
  if (!token) {
    return new Response("Not authenticated", { status: 401 });
  }

  const body = await request.text();
  const backendResponse = await fetch(`${serverBackendUrl}/chat`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      cookie: `${SESSION_COOKIE}=${token.value}`,
    },
    body,
    signal: request.signal,
  });

  return new Response(backendResponse.body, {
    status: backendResponse.status,
    headers: {
      "content-type": backendResponse.headers.get("content-type") ?? "text/event-stream",
    },
  });
}
