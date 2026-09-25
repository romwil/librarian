import { expect, test } from "@playwright/test";
import { loginAsOwner } from "./fixtures/auth";

test.describe("Hall", () => {
  test.beforeEach(async ({ page }) => {
    await loginAsOwner(page);
  });

  test("loads The Hall with shelves region", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByTestId("hall")).toBeVisible();
    await expect(page.getByText("The Hall").first()).toBeVisible();
    // Fresh e2e DATA_DIR: shelves region ready with empty CTA nested inside.
    await expect(page.getByTestId("hall-shelves")).toBeVisible({ timeout: 30_000 });
    await expect(page.getByTestId("hall-empty")).toBeVisible();
  });
});
