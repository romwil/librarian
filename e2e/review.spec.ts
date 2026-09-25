import { expect, test } from "@playwright/test";
import { loginAsOwner } from "./fixtures/auth";

test.describe("Review / bagging area", () => {
  test.beforeEach(async ({ page }) => {
    await loginAsOwner(page);
  });

  test("empty Review shows current bagging empty copy", async ({ page }) => {
    await page.goto("/review");
    await expect(page.getByText("Bagging area").first()).toBeVisible();
    await expect(page.getByRole("heading", { name: "Review" })).toBeVisible();
    // Assert today's empty copy (Phase 4 may rename Holds desk); semantic text, not testid.
    await expect(page.getByText(/bagging area is empty|lamp is quiet/i)).toBeVisible({
      timeout: 30_000,
    });
  });
});
