import { expect, test } from "@playwright/test";
import { dismissWhatsNewIfPresent, loginAsOwner } from "./fixtures/auth";

test.describe("What’s New truth", () => {
  test.beforeEach(async ({ page }) => {
    await loginAsOwner(page);
  });

  test("health reports notes tip lockstep fields", async ({ page }) => {
    const health = await page.request.get("/api/health");
    expect(health.ok()).toBeTruthy();
    const body = await health.json();
    expect(body.version).toBeTruthy();
    expect(body).toHaveProperty("notes_version");
    expect(body).toHaveProperty("notes_match");
  });

  test("Hall still loads after What’s New dismiss", async ({ page }) => {
    await dismissWhatsNewIfPresent(page);
    await page.goto("/");
    await expect(page.getByTestId("hall")).toBeVisible({ timeout: 30_000 });
  });
});
