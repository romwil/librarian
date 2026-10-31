import { expect, type Page } from "@playwright/test";

/** Matches scripts/start-e2e-server.mjs defaults (throwaway, not household secrets). */
export const E2E_OWNER = {
  username: process.env.LIBRARIAN_OWNER_USERNAME || "e2e-owner",
  password: process.env.LIBRARIAN_OWNER_PASSWORD || "e2e-password-ok",
};

/** Dismiss What’s New or reader welcome if either overlay is on top. */
export async function dismissWhatsNewIfPresent(page: Page) {
  // Gates load async — wait briefly so we do not race the backdrop.
  const gotIt = page.getByRole("button", { name: "Got it" });
  const showHall = page.getByRole("button", { name: "Show me the Hall" });
  try {
    await gotIt.or(showHall).waitFor({ state: "visible", timeout: 2500 });
  } catch {
    return;
  }
  if (await gotIt.isVisible()) {
    await gotIt.click();
    await expect(gotIt).toHaveCount(0);
    return;
  }
  await showHall.click();
  await expect(showHall).toHaveCount(0);
}

/** Log in as the seeded e2e owner and land on the Hall. */
export async function loginAsOwner(page: Page, { dismissWhatsNew = true } = {}) {
  await page.goto("/login");
  await expect(page.getByRole("heading", { name: "The Reading Room" })).toBeVisible();
  await page.getByRole("textbox", { name: "Name" }).fill(E2E_OWNER.username);
  await page.getByLabel("Password", { exact: true }).fill(E2E_OWNER.password);
  await page.getByRole("button", { name: "Enter" }).click();
  await expect(page.getByRole("heading", { name: "Hall" })).toBeVisible({
    timeout: 30_000,
  });
  if (dismissWhatsNew) await dismissWhatsNewIfPresent(page);
}
