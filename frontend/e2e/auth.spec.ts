import { expect, test } from "@playwright/test";
import { resetDb, seedUser } from "./helpers/db";
import { addVirtualAuthenticator } from "./helpers/webauthn";
import {
  addPasskey,
  expectSignedIn,
  loginWithPasskey,
  logout,
  registerFromForm,
} from "./helpers/flows";

test.beforeEach(async () => {
  await resetDb();
});

test("an anonymous visitor is redirected to the login box", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByTestId("login-box")).toBeVisible();
  await expect(page.getByTestId("register-link")).toHaveAttribute("href", "/register");
});

test("register, then log out and back in with the same passkey", async ({ page }) => {
  await addVirtualAuthenticator(page);

  await registerFromForm(page, "ada@example.com", "Ada Lovelace");
  await expectSignedIn(page, "ada@example.com");
  await expect(page.locator("p.subtitle")).toContainText("Ada Lovelace");

  await page.goto("/account");
  await logout(page);
  await expect(page.getByTestId("login-box")).toBeVisible();

  await loginWithPasskey(page);
  await expectSignedIn(page, "ada@example.com");
});

test("email is matched case-insensitively when registering", async ({ page }) => {
  await addVirtualAuthenticator(page);
  await registerFromForm(page, "Grace@Example.com", "Grace");
  await expectSignedIn(page, "grace@example.com");

  // A second registration for the same address in another case is rejected.
  await page.context().clearCookies();
  await registerFromForm(page, "grace@example.com", "Impostor");
  await expect(page.getByTestId("register-error")).toContainText(/already exists/i);
});

test("an email claimed mid-ceremony fails the finish with a clear error", async ({ page }) => {
  await addVirtualAuthenticator(page);
  await page.goto("/register");
  await page.getByTestId("register-email").fill("race@example.com");
  await page.getByTestId("register-display-name").fill("Racer");
  await seedUser("race@example.com"); // a concurrent registration wins
  await page.getByTestId("register-submit").click();

  await expect(page.getByTestId("register-error")).toContainText(/already exists/i);
  await expect(page).toHaveURL(/\/register$/);
});

test("account: edit the display name and it persists across a re-login", async ({ page }) => {
  await addVirtualAuthenticator(page);
  await registerFromForm(page, "edit@example.com", "Before");
  await expectSignedIn(page, "edit@example.com");

  await page.goto("/account");
  await page.getByTestId("account-display-name").fill("After");
  await page.getByTestId("account-save").click();
  await expect(page.getByTestId("account-error")).toBeHidden();

  await logout(page);
  await loginWithPasskey(page);
  await expect(page.locator("p.subtitle")).toContainText("After");
});

test("account: add a second passkey, then remove one (never the last)", async ({ page }) => {
  const firstDevice = await addVirtualAuthenticator(page);
  await registerFromForm(page, "keys@example.com", "Keys");
  await expectSignedIn(page, "keys@example.com");

  await page.goto("/account");
  await expect(page.locator(".ant-list-item")).toHaveCount(1);
  await expect(page.getByTestId(/credential-.*-remove/).first()).toBeDisabled();

  // A second device: the first is no longer present (so the new-passkey
  // ceremony can't pick the authenticator that already holds a credential).
  await addVirtualAuthenticator(page);
  await firstDevice.remove();
  await addPasskey(page, "Phone");
  await expect(page.locator(".ant-list-item")).toHaveCount(2);

  const removeButtons = page.getByTestId(/credential-.*-remove/);
  await expect(removeButtons.first()).toBeEnabled();
  await removeButtons.first().click();
  await expect(page.locator(".ant-list-item")).toHaveCount(1);
  await expect(page.getByTestId(/credential-.*-remove/).first()).toBeDisabled();
});

test("a stale session cookie lands on /login without a redirect loop", async ({ page }) => {
  await page.context().addCookies([
    { name: "iv_session", value: "not-a-real-session", domain: "localhost", path: "/" },
  ]);
  await page.goto("/account");
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByTestId("login-box")).toBeVisible();
});
