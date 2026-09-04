import { describe, expect, it } from "vitest";
import { NextRequest } from "next/server";
import { config, middleware } from "@/middleware";

function request(path: string, opts?: { session?: boolean }) {
  const req = new NextRequest(new URL(path, "http://localhost:3000"));
  if (opts?.session) req.cookies.set("iv_session", "token");
  return req;
}

const location = (path: string, opts?: { session?: boolean }) =>
  middleware(request(path, opts)).headers.get("location");

describe("middleware", () => {
  it("sends anonymous visitors of protected routes to /login", () => {
    expect(location("/")).toBe("http://localhost:3000/login");
    expect(location("/account")).toBe("http://localhost:3000/login");
    expect(location("/graph")).toBe("http://localhost:3000/login");
    expect(location("/runs")).toBe("http://localhost:3000/login");
    expect(location("/runs/abc-123")).toBe("http://localhost:3000/login");
  });

  it("lets anyone reach the auth pages (the pages redirect once the session checks out)", () => {
    expect(location("/login")).toBeNull();
    expect(location("/register")).toBeNull();
    expect(location("/login", { session: true })).toBeNull();
  });

  it("lets signed-in visitors through to protected routes", () => {
    expect(location("/", { session: true })).toBeNull();
    expect(location("/account", { session: true })).toBeNull();
    expect(location("/graph", { session: true })).toBeNull();
    expect(location("/runs", { session: true })).toBeNull();
    expect(location("/runs/abc-123", { session: true })).toBeNull();
  });

  it("guards the homepage, account, graph, agent runs pages and both auth pages", () => {
    expect(config.matcher).toEqual([
      "/",
      "/account",
      "/graph",
      "/runs",
      "/runs/:path*",
      "/login",
      "/register",
    ]);
  });
});
