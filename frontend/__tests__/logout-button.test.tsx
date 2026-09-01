import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const { push, refresh, logout } = vi.hoisted(() => ({
  push: vi.fn(),
  refresh: vi.fn(),
  logout: vi.fn(),
}));

vi.mock("next/navigation", () => ({ useRouter: () => ({ push, refresh }) }));
vi.mock("@/lib/auth", () => ({ logout }));

import { LogoutButton } from "@/app/logout-button";

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("LogoutButton", () => {
  it("calls logout and returns to /login", async () => {
    logout.mockResolvedValue({ ok: true });

    render(<LogoutButton />);
    fireEvent.click(screen.getByTestId("logout-button"));

    await waitFor(() => expect(logout).toHaveBeenCalled());
    await waitFor(() => expect(push).toHaveBeenCalledWith("/login"));
  });
});
