import { expect, test, type Page } from "@playwright/test";
import { resetDb } from "./helpers/db";
import { resetGraph } from "./helpers/graph";
import { addVirtualAuthenticator } from "./helpers/webauthn";
import { expectSignedIn, registerFromForm } from "./helpers/flows";

test.beforeEach(async () => {
  await resetDb();
  await resetGraph();
});

async function signUpAndOpenGraph(page: Page, email: string, name: string): Promise<void> {
  await addVirtualAuthenticator(page);
  await registerFromForm(page, email, name);
  await expectSignedIn(page, email);
  await page.goto("/graph");
}

function row(page: Page, name: string) {
  return page.getByTestId("entities-card").getByRole("row", { name: new RegExp(name) });
}

function relRow(page: Page, name: string) {
  return page.getByTestId("relationships-card").getByRole("row", { name: new RegExp(name) });
}

test("the sample-graph button populates the tables and the diagram", async ({ page }) => {
  await signUpAndOpenGraph(page, "sample@example.com", "Sample");

  await page.getByTestId("load-sample-graph").click();

  await expect(row(page, "Acme Corp")).toBeVisible();
  await expect(row(page, "GPT-4")).toBeVisible();
  await expect(relRow(page, "develops")).toBeVisible();
  await expect(page.getByTestId("graph-diagram")).toBeVisible();
});

test("cascade-promotes a connected private sub-graph to public", async ({ page }) => {
  await signUpAndOpenGraph(page, "ada@example.com", "Ada");
  await page.getByTestId("load-sample-graph").click();
  // Sample: "Project Atlas" (private) --works_on-- "Jane Doe" (private).
  await expect(row(page, "Project Atlas")).toContainText("private");
  await expect(row(page, "Jane Doe")).toContainText("private");

  const atlas = row(page, "Project Atlas");
  await atlas.getByRole("checkbox").check(); // cascade to connected
  await atlas.getByRole("switch").click(); // -> public

  await expect(row(page, "Project Atlas")).toContainText("public");
  await expect(row(page, "Jane Doe")).toContainText("public");
});

async function pickOption(page: Page, testId: string, label: string): Promise<void> {
  await page.getByTestId(testId).click();
  // antd keeps closed dropdowns mounted; the just-opened one is the last in the DOM.
  await page.locator(`.ant-select-item-option[title="${label}"]`).last().click();
  await page.keyboard.press("Escape");
}

test("a relationship touching a private entity can't be made public", async ({ page }) => {
  await signUpAndOpenGraph(page, "vis@example.com", "Vis");
  await page.getByTestId("load-sample-graph").click();
  await expect(row(page, "OpenAI")).toBeVisible();

  await pickOption(page, "create-rel-from", "OpenAI");
  await pickOption(page, "create-rel-to", "Project Atlas");

  await expect(page.getByTestId("create-rel-visibility")).toHaveClass(/ant-select-disabled/);

  await page.getByTestId("create-rel-kind").fill("mentions");
  await page.getByTestId("create-rel-submit").click();

  await expect(relRow(page, "mentions")).toContainText("private");
});

test("an owner can delete an entity and its relationships", async ({ page }) => {
  await signUpAndOpenGraph(page, "del@example.com", "Del");
  await page.getByTestId("load-sample-graph").click();
  await expect(row(page, "Jane Doe")).toBeVisible();
  const edgesBefore = await page.getByTestId("relationships-card").getByRole("row").count();

  await row(page, "Jane Doe").getByRole("button", { name: "Delete" }).click();
  await page.getByRole("tooltip").getByRole("button", { name: "Delete" }).click();

  await expect(row(page, "Jane Doe")).toHaveCount(0);
  await expect
    .poll(() => page.getByTestId("relationships-card").getByRole("row").count())
    .toBeLessThan(edgesBefore);
});

test("a second user sees only the public entities", async ({ browser }) => {
  const ownerContext = await browser.newContext();
  const owner = await ownerContext.newPage();
  await signUpAndOpenGraph(owner, "owner@example.com", "Owner");
  await owner.getByTestId("load-sample-graph").click();
  await expect(row(owner, "Acme Corp")).toBeVisible();

  const visitorContext = await browser.newContext();
  const visitor = await visitorContext.newPage();
  await signUpAndOpenGraph(visitor, "visitor@example.com", "Visitor");

  // Public sample entities are visible…
  await expect(row(visitor, "Acme Corp")).toBeVisible();
  await expect(row(visitor, "OpenAI")).toBeVisible();
  // …private ones are not.
  await expect(row(visitor, "Project Atlas")).toHaveCount(0);
  await expect(row(visitor, "Jane Doe")).toHaveCount(0);

  await ownerContext.close();
  await visitorContext.close();
});
