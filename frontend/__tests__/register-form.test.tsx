import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const { push, refresh, registerPasskey } = vi.hoisted(() => ({
  push: vi.fn(),
  refresh: vi.fn(),
  registerPasskey: vi.fn(),
}));

vi.mock("next/navigation", () => ({ useRouter: () => ({ push, refresh }) }));
vi.mock("@/lib/auth", () => ({ registerPasskey }));

import { RegisterForm } from "@/app/register/register-form";

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

function fillForm() {
  fireEvent.change(screen.getByTestId("register-email"), {
    target: { value: "ada@example.com" },
  });
  fireEvent.change(screen.getByTestId("register-display-name"), {
    target: { value: "Ada" },
  });
}

describe("RegisterForm", () => {
  it("submits email + display name and navigates home", async () => {
    registerPasskey.mockResolvedValue({
      ok: true,
      data: { id: "1", email: "ada@example.com", display_name: "Ada" },
    });

    render(<RegisterForm />);
    fillForm();
    fireEvent.click(screen.getByTestId("register-submit"));

    await waitFor(() =>
      expect(registerPasskey).toHaveBeenCalledWith("ada@example.com", "Ada"),
    );
    await waitFor(() => expect(push).toHaveBeenCalledWith("/"));
  });

  it("surfaces a backend error", async () => {
    registerPasskey.mockResolvedValue({ ok: false, error: "An account with that email already exists" });

    render(<RegisterForm />);
    fillForm();
    fireEvent.click(screen.getByTestId("register-submit"));

    expect(await screen.findByTestId("register-error")).toHaveTextContent(
      "An account with that email already exists",
    );
    expect(push).not.toHaveBeenCalled();
  });

  it("does not call the backend when the email is invalid", async () => {
    render(<RegisterForm />);
    fireEvent.change(screen.getByTestId("register-email"), {
      target: { value: "not-an-email" },
    });
    fireEvent.change(screen.getByTestId("register-display-name"), {
      target: { value: "Ada" },
    });
    fireEvent.click(screen.getByTestId("register-submit"));

    expect(await screen.findByText("Enter a valid email")).toBeInTheDocument();
    expect(registerPasskey).not.toHaveBeenCalled();
  });
});
