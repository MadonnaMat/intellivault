import { NextResponse, type NextRequest } from "next/server";

const SESSION_COOKIE = "iv_session";
const PUBLIC_PATHS = new Set(["/login", "/register"]);

/**
 * Cookie-presence gate. Real session validation happens server-side in each
 * protected page (which calls the backend `/auth/me`); this only keeps signed-out
 * visitors on the auth pages and signed-in ones off them.
 */
export function middleware(request: NextRequest) {
  const hasSession = request.cookies.has(SESSION_COOKIE);
  const isPublic = PUBLIC_PATHS.has(request.nextUrl.pathname);

  if (!hasSession && !isPublic) {
    return NextResponse.redirect(new URL("/login", request.url));
  }
  if (hasSession && isPublic) {
    return NextResponse.redirect(new URL("/", request.url));
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/", "/account", "/login", "/register"],
};
