import { expect, test } from "@playwright/test";
import { loginAsOwner } from "./fixtures/auth";

test.describe("Settings nav", () => {
  test.beforeEach(async ({ page }) => {
    await loginAsOwner(page);
  });

  test("Settings page exposes section nav and Appearance panel", async ({ page }) => {
    await page.goto("/settings");
    await expect(page.getByRole("heading", { name: "Settings" })).toBeVisible({ timeout: 30_000 });
    await expect(page.getByRole("navigation", { name: "Settings sections" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Appearance" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Bagging" })).toBeVisible();
    await page.getByRole("button", { name: "Appearance" }).click();
    await expect(page.getByText("Your appearance")).toBeVisible();
    await expect(page.getByRole("slider", { name: "Text size" })).toBeVisible();
  });
});
