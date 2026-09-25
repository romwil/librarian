import { expect, test } from "@playwright/test";
import { loginAsOwner } from "./fixtures/auth";

test.describe("Review / bagging area", () => {
  test.beforeEach(async ({ page }) => {
    await loginAsOwner(page);
  });

  test("empty Review shows current bagging empty copy", async ({ page }) => {
    await page.goto("/review");
    await expect(page.getByText("Bagging area").first()).toBeVisible();
    // Assert today's copy (Phase 4 will rename Holds desk); prefer testid over brittle full string.
    const empty = page.getByTestId("review-empty");
    await expect(empty).toBeVisible({ timeout: 30_000 });
    await expect(empty).toContainText(/bagging area is empty|lamp is quiet/i);
  });
});
