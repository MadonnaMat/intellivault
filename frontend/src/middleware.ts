import { NextResponse, type NextRequest } from "next/server";
import { SESSION_COOKIE } from "@/lib/backend";

const PUBLIC_PATHS = new Set(["/login", "/register"]);

/**
 * Cheap gate: bounce visitors with no session cookie off the protected routes.
 * The reverse direction (sending signed-in users away from /login and /register)
 * is handled in those pages after they validate the session server-side — doing
 * it here on cookie presence alone would loop when the cookie is stale.
 */
export function middleware(request: NextRequest) {
  const hasSession = request.cookies.has(SESSION_COOKIE);
  const isPublic = PUBLIC_PATHS.has(request.nextUrl.pathname);

  if (!hasSession && !isPublic) {
    return NextResponse.redirect(new URL("/login", request.url));
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/", "/account", "/login", "/register"],
};
