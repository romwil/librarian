import { expect, test } from "@playwright/test";
import { dismissWhatsNewIfPresent, loginAsOwner } from "./fixtures/auth";

test.describe("Notifications inbox + prefs", () => {
  test.beforeEach(async ({ page }) => {
    await loginAsOwner(page);
  });

  test("Settings Notifications section is reachable", async ({ page }) => {
    await page.goto("/settings");
    await expect(page.getByRole("heading", { name: "Settings" })).toBeVisible({ timeout: 30_000 });
    await dismissWhatsNewIfPresent(page);
    await page.getByRole("button", { name: "Notifications" }).click();
    await expect(page.getByRole("heading", { name: "What the house tells you" })).toBeVisible();
    await expect(page.getByLabel("Notification email")).toBeVisible();
    await expect(page.getByLabel("Enable Arrived (your Request)")).toBeVisible();
    await expect(page.getByRole("button", { name: "Save preferences" })).toBeVisible();
  });

  test("Inbox empty state and top-bar entry", async ({ page }) => {
    await page.goto("/");
    await dismissWhatsNewIfPresent(page);
    await expect(page.getByRole("link", { name: "Inbox" })).toBeVisible();
    await page.getByRole("link", { name: "Inbox" }).click();
    await expect(page.getByRole("heading", { name: "Inbox" })).toBeVisible({ timeout: 30_000 });
    await expect(page.getByText("The desk is clear.")).toBeVisible();
    await expect(page.getByRole("link", { name: "Notification preferences" })).toBeVisible();
  });

  test("Profile Notifications page loads kind prefs", async ({ page }) => {
    await page.goto("/notifications");
    await dismissWhatsNewIfPresent(page);
    await expect(page.getByRole("heading", { name: "Notifications" })).toBeVisible({ timeout: 30_000 });
    await expect(page.getByLabel("Enable Needs you (Review)")).toBeVisible();
    await expect(page.getByLabel("Timing for Quiet hours wake")).toBeVisible();
  });

  test("Library newsletter cadence and owner early push", async ({ page }) => {
    await page.goto("/notifications");
    await dismissWhatsNewIfPresent(page);
    await expect(page.getByRole("heading", { name: "Send an edition early" })).toBeVisible({
      timeout: 30_000,
    });
    await expect(page.getByLabel("Newsletter send scope")).toBeVisible();
    await expect(page.getByRole("button", { name: "Send library letter now" })).toBeVisible();
    await expect(page.getByLabel("Enable Library newsletter")).toBeVisible();
    await page.getByLabel("Enable Library newsletter").check();
    const cadence = page.getByLabel("Cadence for Library newsletter");
    await expect(cadence).toBeEnabled();
    await cadence.selectOption("monthly");
    await expect(cadence).toHaveValue("monthly");
  });
});
