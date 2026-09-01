import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const { push, refresh, loginPasskey } = vi.hoisted(() => ({
  push: vi.fn(),
  refresh: vi.fn(),
  loginPasskey: vi.fn(),
}));

vi.mock("next/navigation", () => ({ useRouter: () => ({ push, refresh }) }));
vi.mock("@/lib/auth", () => ({ loginPasskey }));

import { LoginBox } from "@/app/login/login-box";

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("LoginBox", () => {
  it("navigates to the homepage on a successful sign-in", async () => {
    loginPasskey.mockResolvedValue({
      ok: true,
      data: { id: "1", email: "a@b.com", display_name: "Ada" },
    });

    render(<LoginBox />);
    fireEvent.click(screen.getByTestId("login-submit"));

    await waitFor(() => expect(push).toHaveBeenCalledWith("/"));
  });

  it("shows the error and stays put on failure", async () => {
    loginPasskey.mockResolvedValue({ ok: false, error: "Unknown passkey" });

    render(<LoginBox />);
    fireEvent.click(screen.getByTestId("login-submit"));

    expect(await screen.findByTestId("login-error")).toHaveTextContent("Unknown passkey");
    expect(push).not.toHaveBeenCalled();
  });

  it("links to the registration page", () => {
    render(<LoginBox />);
    expect(screen.getByTestId("register-link")).toHaveAttribute("href", "/register");
  });
});
