import { afterEach, describe, expect, it, vi } from "vitest";

const { cookieGet, redirect, requestJson } = vi.hoisted(() => ({
  cookieGet: vi.fn(),
  redirect: vi.fn(),
  requestJson: vi.fn(),
}));

vi.mock("server-only", () => ({}));
vi.mock("next/headers", () => ({ cookies: async () => ({ get: cookieGet }) }));
vi.mock("next/navigation", () => ({ redirect }));
vi.mock("@/lib/api", () => ({ requestJson }));

import { currentUser, redirectIfAuthenticated } from "@/lib/session";

const user = { id: "1", email: "a@b.com", display_name: "Ada" };

afterEach(() => vi.clearAllMocks());

describe("currentUser", () => {
  it("returns null when there is no cookie", async () => {
    cookieGet.mockReturnValue(undefined);
    expect(await currentUser()).toBeNull();
    expect(requestJson).not.toHaveBeenCalled();
  });

  it("returns the user on 200", async () => {
    cookieGet.mockReturnValue({ value: "tok" });
    requestJson.mockResolvedValue({ status: 200, ok: true, body: user });
    expect(await currentUser()).toEqual(user);
  });

  it("returns null on 401", async () => {
    cookieGet.mockReturnValue({ value: "stale" });
    requestJson.mockResolvedValue({ status: 401, ok: false, body: { detail: "no" } });
    expect(await currentUser()).toBeNull();
  });

  it("throws on a backend error (does not look like a logout)", async () => {
    cookieGet.mockReturnValue({ value: "tok" });
    requestJson.mockResolvedValue({ status: 503, ok: false, body: undefined, error: "boom" });
    await expect(currentUser()).rejects.toThrow();
  });
});

describe("redirectIfAuthenticated", () => {
  it("redirects to / when a session resolves", async () => {
    cookieGet.mockReturnValue({ value: "tok" });
    requestJson.mockResolvedValue({ status: 200, ok: true, body: user });
    await redirectIfAuthenticated();
    expect(redirect).toHaveBeenCalledWith("/");
  });

  it("does nothing for an anonymous visitor", async () => {
    cookieGet.mockReturnValue(undefined);
    await redirectIfAuthenticated();
    expect(redirect).not.toHaveBeenCalled();
  });
});
