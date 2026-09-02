import { beforeEach, describe, expect, it, vi } from "vitest";

const apiFetch = vi.fn();
vi.mock("@/lib/api", () => ({ apiFetch: (...args: unknown[]) => apiFetch(...args) }));

import {
  createEntity,
  createRelationship,
  fetchGraph,
  seedSampleGraph,
  setEntityVisibility,
} from "@/lib/graph";

const AUTHED = { authed: true };

beforeEach(() => {
  apiFetch.mockReset();
  apiFetch.mockResolvedValue({ ok: true, status: 200, data: { id: "generated" } });
});

describe("graph lib wrappers", () => {
  it("fetchGraph GETs /graph as an authed call", async () => {
    await fetchGraph();
    expect(apiFetch).toHaveBeenCalledWith("/graph", undefined, AUTHED);
  });

  it("createEntity POSTs the input body", async () => {
    const input = { name: "Acme", kind: "org", visibility: "public", attributes: {} } as const;
    await createEntity(input);
    expect(apiFetch).toHaveBeenCalledWith(
      "/graph/entities",
      { method: "POST", body: JSON.stringify(input) },
      AUTHED,
    );
  });

  it("setEntityVisibility PATCHes with the id in the path", async () => {
    await setEntityVisibility("e1", { visibility: "public", cascade: true });
    expect(apiFetch).toHaveBeenCalledWith(
      "/graph/entities/e1/visibility",
      { method: "PATCH", body: JSON.stringify({ visibility: "public", cascade: true }) },
      AUTHED,
    );
  });

  it("seedSampleGraph creates every sample entity then every link", async () => {
    await seedSampleGraph();
    const paths = apiFetch.mock.calls.map((call) => call[0]);
    expect(paths.filter((p) => p === "/graph/entities")).toHaveLength(5);
    expect(paths.filter((p) => p === "/graph/relationships")).toHaveLength(5);
  });

  it("seedSampleGraph stops and returns the first failure", async () => {
    apiFetch.mockResolvedValueOnce({ ok: false, status: 500, error: "boom" });
    const result = await seedSampleGraph();
    expect(result.ok).toBe(false);
    expect(apiFetch).toHaveBeenCalledTimes(1);
  });

  it("createRelationship POSTs the input body", async () => {
    const input = { from_id: "a", to_id: "b", kind: "employs", visibility: "private" } as const;
    await createRelationship(input);
    expect(apiFetch).toHaveBeenCalledWith(
      "/graph/relationships",
      { method: "POST", body: JSON.stringify(input) },
      AUTHED,
    );
  });
});
