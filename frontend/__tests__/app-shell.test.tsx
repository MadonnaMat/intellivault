import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
  usePathname: () => "/graph",
}));

import { AppShell } from "@/app/app-shell";

const user = { id: "u1", email: "ada@example.com", display_name: "Ada" };

afterEach(() => {
  cleanup();
});

describe("AppShell", () => {
  it("renders nav links to every section", () => {
    render(
      <AppShell user={user}>
        <p>content</p>
      </AppShell>,
    );

    expect(screen.getByTestId("nav-chat")).toHaveAttribute("href", "/");
    expect(screen.getByTestId("nav-graph")).toHaveAttribute("href", "/graph");
    expect(screen.getByTestId("nav-runs")).toHaveAttribute("href", "/runs");
    expect(screen.getByTestId("nav-account")).toHaveAttribute("href", "/account");
  });

  it("marks the current route active", () => {
    render(
      <AppShell user={user}>
        <p>content</p>
      </AppShell>,
    );

    expect(screen.getByTestId("nav-graph")).toHaveAttribute("aria-current", "page");
    expect(screen.getByTestId("nav-chat")).not.toHaveAttribute("aria-current");
  });

  it("shows the signed-in user and a logout button", () => {
    render(
      <AppShell user={user}>
        <p>content</p>
      </AppShell>,
    );

    expect(screen.getByTestId("app-shell-user")).toHaveTextContent("Ada");
    expect(screen.getByTestId("logout-button")).toBeInTheDocument();
  });

  it("renders the wrapped content", () => {
    render(
      <AppShell user={user}>
        <p data-testid="page-content">content</p>
      </AppShell>,
    );

    expect(screen.getByTestId("page-content")).toBeInTheDocument();
  });
});
