import { expect, test } from "@playwright/test";
import { dismissWhatsNewIfPresent, loginAsOwner } from "./fixtures/auth";

test.describe("What’s New truth", () => {
  test.beforeEach(async ({ page }) => {
    await loginAsOwner(page);
  });

  test("owner status reports notes tip lockstep from the image", async ({ page }) => {
    const health = await page.request.get("/api/health");
    expect(health.ok()).toBeTruthy();
    expect(await health.json()).toEqual({ status: "ok" });

    const status = await page.request.get("/api/status");
    expect(status.ok()).toBeTruthy();
    const body = await status.json();
    expect(body.version).toBeTruthy();
    expect(body.notes_match).toBe(true);
  });

  test("Hall still loads after What’s New dismiss", async ({ page }) => {
    await dismissWhatsNewIfPresent(page);
    await page.goto("/");
    await expect(page.getByTestId("hall")).toBeVisible({ timeout: 30_000 });
  });
});
