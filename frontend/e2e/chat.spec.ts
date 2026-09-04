import { expect, test } from "@playwright/test";
import { resetDb } from "./helpers/db";
import { resetGraph } from "./helpers/graph";
import { addVirtualAuthenticator } from "./helpers/webauthn";
import { registerFromForm, expectSignedIn } from "./helpers/flows";

/**
 * The chat -> tool-call -> background agent -> review -> graph loop, driven
 * entirely through the UI. Unlike agent.spec.ts (which drives the agent via
 * page.request and never touches the UI), this closes the loop through the
 * real chat page, the Agent Runs pages, and back to /graph. mock-ai stands in
 * for Ollama (docker-compose.e2e.yml), so this needs no GPU and no network —
 * see docker/mock-ai/llm.json for the launch_research_agent tool-call fixture.
 */

const TOPIC = "The invention of the transistor at Bell Labs";

test.beforeEach(async () => {
  await resetDb();
  await resetGraph();
});

test("a chat research request launches the agent, and the loop closes through the UI", async ({
  page,
}) => {
  await addVirtualAuthenticator(page);
  await registerFromForm(page, "chat@example.com", "Chat User");
  await expectSignedIn(page, "chat@example.com");

  await page.getByTestId("chat-input").fill(`Please research ${TOPIC}.`);
  await page.getByTestId("chat-send").click();

  const runCard = page.getByTestId("chat-run-card");
  await expect(runCard).toBeVisible({ timeout: 15_000 });
  await expect(runCard).toContainText(TOPIC);

  // Follow the card's own link into the run's detail page.
  await runCard.getByRole("link", { name: /view progress/i }).click();
  await expect(page).toHaveURL(/\/runs\/.+/);

  // AGENT_REVIEW_REQUIRED defaults to true, so the run parks for review.
  await expect(page.getByTestId("run-status")).toHaveText("awaiting_review", { timeout: 30_000 });
  await expect(page.getByTestId("run-review-approve")).toBeVisible();
  await page.getByTestId("run-review-approve").click();

  await expect(page.getByTestId("run-status")).toHaveText("succeeded", { timeout: 30_000 });
  await expect(page.getByTestId("run-result")).toContainText("Bell Labs");

  // The run also shows up in the list.
  await page.getByTestId("nav-runs").click();
  await expect(page.getByTestId("runs-table")).toContainText(TOPIC);
  await expect(page.getByTestId("runs-table")).toContainText("succeeded");

  // And its committed entities are on the caller's private graph.
  await page.goto("/graph");
  const entities = page.getByTestId("entities-card");
  await expect(entities.getByRole("row", { name: /Bell Labs/ })).toContainText("private");
  await expect(entities.getByRole("row", { name: /William Shockley/ })).toBeVisible();
});
