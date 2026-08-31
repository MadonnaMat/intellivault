import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { HealthCard } from "@/app/health-card";
import type { HealthResponse } from "@/lib/health";

afterEach(cleanup);

const okResponse: HealthResponse = {
  status: "ok",
  services: [
    { name: "postgres", ok: true, degraded: false, detail: "SELECT 1", latency_ms: 12 },
    { name: "ollama", ok: true, degraded: true, detail: "missing model", latency_ms: 8 },
  ],
};

const downResponse: HealthResponse = {
  status: "down",
  services: [
    { name: "postgres", ok: false, degraded: false, detail: "ConnectionError", latency_ms: 30 },
  ],
};

describe("HealthCard", () => {
  it("renders overall status and one row per service", () => {
    render(<HealthCard initial={{ ok: true, data: okResponse }} />);

    expect(screen.getByTestId("health-status")).toHaveTextContent("ok");
    expect(screen.getByTestId("service-postgres")).toBeInTheDocument();
    expect(screen.getByTestId("service-postgres-status")).toHaveTextContent("ok");
    expect(screen.getByTestId("service-ollama-status")).toHaveTextContent("degraded");
    expect(screen.getByTestId("service-postgres-detail")).toHaveTextContent("SELECT 1");
  });

  it("shows an error when the backend was unreachable", () => {
    render(<HealthCard initial={{ ok: false, error: "fetch failed" }} />);

    expect(screen.getByTestId("health-status")).toHaveTextContent("unreachable");
    expect(screen.getByTestId("health-error")).toHaveTextContent("fetch failed");
  });

  it("re-fetches on Refresh and reflects the new status", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(new Response(JSON.stringify(downResponse), { status: 503 }));

    render(<HealthCard initial={{ ok: true, data: okResponse }} />);
    fireEvent.click(screen.getByTestId("refresh-button"));

    expect(await screen.findByTestId("service-postgres-status")).toHaveTextContent("down");
    expect(screen.getByTestId("health-status")).toHaveTextContent("down");
    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/health",
      expect.objectContaining({ cache: "no-store" }),
    );
    fetchMock.mockRestore();
  });
});
