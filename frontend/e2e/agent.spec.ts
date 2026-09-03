import { expect, test } from "@playwright/test";
import { resetDb } from "./helpers/db";
import { resetGraph } from "./helpers/graph";
import { addVirtualAuthenticator } from "./helpers/webauthn";
import { expectSignedIn, registerFromForm } from "./helpers/flows";

/**
 * The agent loop, driven through the real stack: POST /agent/runs -> Redis ->
 * the agent-worker container -> LangGraph -> private entities in Neo4j. The
 * worker's Ollama + web-search MCP are the mock-ai container
 * (docker-compose.e2e.yml), so no GPU or network is involved.
 */

const BACKEND = process.env.E2E_BACKEND_URL ?? "http://localhost:8000";

test.beforeEach(async () => {
  await resetDb(); // TRUNCATE users CASCADE also clears agent_runs
  await resetGraph();
});

test("a run turns a topic into the caller's private graph entities", async ({ page }) => {
  await addVirtualAuthenticator(page);
  await registerFromForm(page, "agent@example.com", "Agent User");
  await expectSignedIn(page, "agent@example.com");

  const created = await page.request.post(`${BACKEND}/agent/runs`, {
    data: { topic: "The invention of the transistor at Bell Labs" },
  });
  expect(created.status()).toBe(202);
  const { id } = (await created.json()) as { id: string };

  await expect
    .poll(
      async () => {
        const res = await page.request.get(`${BACKEND}/agent/runs/${id}`);
        return (await res.json()).status as string;
      },
      { timeout: 60_000, intervals: [1_000] },
    )
    .toBe("succeeded");

  const run = await (await page.request.get(`${BACKEND}/agent/runs/${id}`)).json();
  expect(run.result.entities_created).toBeGreaterThan(0);
  expect(run.committed_entity_ids.length).toBe(run.result.entities_created);

  // The new entities are private and show on the caller's graph page.
  await page.goto("/graph");
  const entities = page.getByTestId("entities-card");
  await expect(entities.getByRole("row", { name: /Bell Labs/ })).toContainText("private");
  await expect(entities.getByRole("row", { name: /William Shockley/ })).toBeVisible();
  await expect(
    page.getByTestId("relationships-card").getByRole("row", { name: /worked_at/ }).first(),
  ).toBeVisible();
});

test("another user cannot see a run's private entities", async ({ browser }) => {
  const runnerCtx = await browser.newContext();
  const runner = await runnerCtx.newPage();
  await addVirtualAuthenticator(runner);
  await registerFromForm(runner, "runner@example.com", "Runner");
  await expectSignedIn(runner, "runner@example.com");

  const created = await runner.request.post(`${BACKEND}/agent/runs`, {
    data: { topic: "The invention of the transistor at Bell Labs" },
  });
  const { id } = (await created.json()) as { id: string };
  await expect
    .poll(
      async () =>
        (await (await runner.request.get(`${BACKEND}/agent/runs/${id}`)).json()).status as string,
      { timeout: 60_000, intervals: [1_000] },
    )
    .toBe("succeeded");

  const visitorCtx = await browser.newContext();
  const visitor = await visitorCtx.newPage();
  await addVirtualAuthenticator(visitor);
  await registerFromForm(visitor, "visitor@example.com", "Visitor");
  await expectSignedIn(visitor, "visitor@example.com");

  await visitor.goto("/graph");
  await expect(
    visitor.getByTestId("entities-card").getByRole("row", { name: /Bell Labs/ }),
  ).toHaveCount(0);

  // The run is the runner's own; a visitor can't read it either.
  expect((await visitor.request.get(`${BACKEND}/agent/runs/${id}`)).status()).toBe(404);

  await runnerCtx.close();
  await visitorCtx.close();
});
