import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { HealthCard } from "@/app/health-card";
import type { HealthResponse, HealthResult } from "@/lib/health";

afterEach(cleanup);

const okResponse: HealthResponse = {
  status: "ok",
  services: [
    { name: "postgres", ok: true, degraded: false, detail: "SELECT 1", latency_ms: 12 },
    { name: "ollama", ok: true, degraded: false, detail: "models present", latency_ms: 8 },
  ],
};

const downResponse: HealthResponse = {
  status: "down",
  services: [
    { name: "postgres", ok: false, degraded: false, detail: "ConnectionError", latency_ms: 30 },
  ],
};

describe("HealthCard", () => {
  it("renders each service from the initial result", () => {
    render(<HealthCard initial={{ ok: true, data: okResponse }} />);
    expect(screen.getByText("ok")).toBeInTheDocument();
    expect(screen.getByText(/postgres/)).toBeInTheDocument();
    expect(screen.getByText(/ollama/)).toBeInTheDocument();
  });

  it("shows an error when the backend was unreachable", () => {
    render(<HealthCard initial={{ ok: false, error: "fetch failed" }} />);
    expect(screen.getByText(/Could not reach the backend/)).toBeInTheDocument();
    expect(screen.getByText("unreachable")).toBeInTheDocument();
  });

  it("re-fetches on Refresh and reflects the new status", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(new Response(JSON.stringify(downResponse), { status: 503 }));

    render(<HealthCard initial={{ ok: true, data: okResponse }} />);
    fireEvent.click(screen.getByRole("button", { name: "Refresh" }));

    expect(await screen.findByText("down")).toBeInTheDocument();
    fetchMock.mockRestore();
  });
});

// Type-only guard: ServiceStatus shape is what the component consumes.
const _typecheck: HealthResult = { ok: true, data: okResponse };
void _typecheck;
