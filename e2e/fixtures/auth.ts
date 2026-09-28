import { expect, type Page } from "@playwright/test";

/** Matches scripts/start-e2e-server.mjs defaults (throwaway, not household secrets). */
export const E2E_OWNER = {
  username: process.env.LIBRARIAN_OWNER_USERNAME || "e2e-owner",
  password: process.env.LIBRARIAN_OWNER_PASSWORD || "e2e-password-ok",
};

/** Dismiss What’s New if it appears after first login for this runtime version. */
export async function dismissWhatsNewIfPresent(page: Page) {
  // Gate loads release notes async — wait briefly so we do not race the backdrop.
  const gotIt = page.getByRole("button", { name: "Got it" });
  try {
    await gotIt.waitFor({ state: "visible", timeout: 2500 });
  } catch {
    return;
  }
  await gotIt.click();
  await expect(gotIt).toHaveCount(0);
}

/** Log in as the seeded e2e owner and land on the Hall. */
export async function loginAsOwner(page: Page) {
  await page.goto("/login");
  await expect(page.getByRole("heading", { name: "The Reading Room" })).toBeVisible();
  await page.getByRole("textbox", { name: "Name" }).fill(E2E_OWNER.username);
  await page.getByRole("textbox", { name: "Password" }).fill(E2E_OWNER.password);
  await page.getByRole("button", { name: "Enter" }).click();
  await expect(page.getByRole("heading", { name: "What are you looking for?" })).toBeVisible({
    timeout: 30_000,
  });
  await dismissWhatsNewIfPresent(page);
}
