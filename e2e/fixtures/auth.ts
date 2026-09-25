import { expect, type Page } from "@playwright/test";

/** Matches scripts/start-e2e-server.mjs defaults (throwaway, not household secrets). */
export const E2E_OWNER = {
  username: process.env.LIBRARIAN_OWNER_USERNAME || "e2e-owner",
  password: process.env.LIBRARIAN_OWNER_PASSWORD || "e2e-password-ok",
};

/** Dismiss What’s New if it appears after first login for this runtime version. */
export async function dismissWhatsNewIfPresent(page: Page) {
  const modal = page.getByTestId("whats-new-modal");
  if (await modal.isVisible().catch(() => false)) {
    await page.getByTestId("whats-new-got-it").click();
    await expect(modal).toHaveCount(0);
  }
}

/** Log in as the seeded e2e owner and land on the Hall. */
export async function loginAsOwner(page: Page) {
  await page.goto("/login");
  await expect(page.getByRole("heading", { name: "The Reading Room" })).toBeVisible();
  await page.locator("#login-name").fill(E2E_OWNER.username);
  await page.locator("#login-pass").fill(E2E_OWNER.password);
  await page.getByRole("button", { name: "Enter" }).click();
  await expect(page.getByTestId("hall")).toBeVisible({ timeout: 30_000 });
  await dismissWhatsNewIfPresent(page);
}
