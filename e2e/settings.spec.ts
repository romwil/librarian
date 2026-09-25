import { expect, test } from "@playwright/test";
import { loginAsOwner } from "./fixtures/auth";

test.describe("Settings nav", () => {
  test.beforeEach(async ({ page }) => {
    await loginAsOwner(page);
  });

  test("Settings page exposes section nav and Appearance panel", async ({ page }) => {
    await page.goto("/settings");
    await expect(page.getByTestId("settings-page")).toBeVisible({ timeout: 30_000 });
    await expect(page.getByTestId("settings-section-nav")).toBeVisible();
    await expect(page.getByTestId("settings-nav-appearance")).toBeVisible();
    await expect(page.getByTestId("settings-nav-bagging")).toBeVisible();
    await page.getByTestId("settings-nav-appearance").click();
    await expect(page.getByTestId("settings-panel-appearance")).toBeVisible();
  });
});
