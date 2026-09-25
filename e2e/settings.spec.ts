import { expect, test } from "@playwright/test";
import { dismissWhatsNewIfPresent, loginAsOwner } from "./fixtures/auth";

test.describe("Settings nav", () => {
  test.beforeEach(async ({ page }) => {
    await loginAsOwner(page);
  });

  test("Settings page exposes section nav and Appearance panel", async ({ page }) => {
    await page.goto("/settings");
    await dismissWhatsNewIfPresent(page);
    await expect(page.getByRole("heading", { name: "Settings" })).toBeVisible({ timeout: 30_000 });
    await expect(page.getByRole("navigation", { name: "Settings sections" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Appearance" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Shelving" })).toBeVisible();
    await page.getByRole("button", { name: "Appearance" }).click();
    await expect(page.getByText("Your appearance")).toBeVisible();
    await expect(page.getByRole("slider", { name: "Text size" })).toBeVisible();
  });

  test("Library card menu opens from the top bar", async ({ page }) => {
    await page.goto("/");
    await dismissWhatsNewIfPresent(page);
    await page.getByRole("button", { name: "Library card" }).click();
    await expect(page.getByRole("menu")).toBeVisible();
    await expect(page.getByRole("menuitem", { name: "Inbox" })).toBeVisible();
    await expect(page.getByRole("radiogroup", { name: "Theme" })).toBeVisible();
  });

  test("Settings Mail section is reachable from nav", async ({ page }) => {
    await page.goto("/settings");
    await dismissWhatsNewIfPresent(page);
    await expect(page.getByRole("heading", { name: "Settings" })).toBeVisible({ timeout: 30_000 });
    await page.getByRole("button", { name: "Mail" }).click();
    await expect(page.getByRole("heading", { name: "Outbound email" })).toBeVisible();
    await expect(page.getByLabel("Provider")).toBeVisible();
    await expect(page.getByRole("button", { name: "Send test email" })).toBeVisible();
  });
});
