import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { CredentialSummary } from "@/lib/auth";

const { refresh, updateAccount, addPasskey, removeCredential } = vi.hoisted(() => ({
  refresh: vi.fn(),
  updateAccount: vi.fn(),
  addPasskey: vi.fn(),
  removeCredential: vi.fn(),
}));

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), refresh }) }));
vi.mock("@/lib/auth", () => ({ updateAccount, addPasskey, removeCredential }));

import { AccountView } from "@/app/account/account-view";

const user = { id: "u1", email: "ada@example.com", display_name: "Ada" };

function credential(overrides: Partial<CredentialSummary> = {}): CredentialSummary {
  return {
    id: "c1",
    name: "Laptop",
    created_at: "2026-01-01T00:00:00Z",
    last_used_at: null,
    transports: ["internal"],
    ...overrides,
  };
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("AccountView", () => {
  it("saves profile edits", async () => {
    updateAccount.mockResolvedValue({ ok: true, data: user });
    render(<AccountView user={user} credentials={[credential()]} />);

    fireEvent.change(screen.getByTestId("account-display-name"), {
      target: { value: "Ada L" },
    });
    fireEvent.click(screen.getByTestId("account-save"));

    await waitFor(() =>
      expect(updateAccount).toHaveBeenCalledWith({
        email: "ada@example.com",
        displayName: "Ada L",
      }),
    );
    await waitFor(() => expect(refresh).toHaveBeenCalled());
  });

  it("disables Remove when only one passkey remains", () => {
    render(<AccountView user={user} credentials={[credential()]} />);
    expect(screen.getByTestId("credential-c1-remove")).toBeDisabled();
  });

  it("removes a passkey when more than one exists", async () => {
    removeCredential.mockResolvedValue({ ok: true });
    render(
      <AccountView
        user={user}
        credentials={[credential(), credential({ id: "c2", name: "Phone" })]}
      />,
    );

    const remove = screen.getByTestId("credential-c2-remove");
    expect(remove).not.toBeDisabled();
    fireEvent.click(remove);

    await waitFor(() => expect(removeCredential).toHaveBeenCalledWith("c2"));
  });

  it("shows an error when a passkey cannot be removed", async () => {
    removeCredential.mockResolvedValue({ ok: false, error: "You must keep at least one passkey" });
    render(
      <AccountView
        user={user}
        credentials={[credential(), credential({ id: "c2" })]}
      />,
    );

    fireEvent.click(screen.getByTestId("credential-c2-remove"));

    expect(await screen.findByTestId("account-error")).toHaveTextContent(
      "You must keep at least one passkey",
    );
  });

  it("adds a named passkey through the modal", async () => {
    addPasskey.mockResolvedValue({ ok: true, data: credential({ id: "c9", name: "Work" }) });
    render(<AccountView user={user} credentials={[credential()]} />);

    fireEvent.click(screen.getByTestId("add-passkey-button"));
    fireEvent.change(await screen.findByTestId("add-passkey-name"), {
      target: { value: "Work" },
    });
    fireEvent.click(screen.getByText("Continue"));

    await waitFor(() => expect(addPasskey).toHaveBeenCalledWith("Work"));
  });
});
