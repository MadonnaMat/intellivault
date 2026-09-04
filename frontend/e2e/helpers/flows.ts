import { expect, type Page } from "@playwright/test";

const HOME = "/";

export async function registerFromForm(
  page: Page,
  email: string,
  displayName: string,
): Promise<void> {
  await page.goto("/register");
  await page.getByTestId("register-email").fill(email);
  await page.getByTestId("register-display-name").fill(displayName);
  await page.getByTestId("register-submit").click();
}

export async function expectSignedIn(page: Page, email: string): Promise<void> {
  await expect(page).toHaveURL(HOME);
  await expect(page.getByTestId("app-shell-user")).toContainText(email);
}

export async function loginWithPasskey(page: Page): Promise<void> {
  await page.goto("/login");
  await page.getByTestId("login-submit").click();
}

export async function logout(page: Page): Promise<void> {
  await page.getByTestId("logout-button").click();
  await expect(page).toHaveURL(/\/login$/);
}

export async function addPasskey(page: Page, name: string): Promise<void> {
  await page.goto("/account");
  const rows = page.getByTestId("passkeys-list").locator(".ant-list-item");
  const before = await rows.count();
  await page.getByTestId("add-passkey-button").click();
  await page.getByTestId("add-passkey-name").fill(name);
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page.getByTestId("account-error")).toBeHidden();
  await expect(rows).toHaveCount(before + 1);
}
