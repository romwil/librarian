import { expect, test } from "@playwright/test";
import { loginAsOwner } from "./fixtures/auth";

test.describe("Hall", () => {
  test.beforeEach(async ({ page }) => {
    await loginAsOwner(page);
  });

  test("loads The Hall with shelves region", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByText("The Hall").first()).toBeVisible();
    await expect(page.getByRole("heading", { name: "What are you looking for?" })).toBeVisible();
    // Fresh e2e DATA_DIR: empty Hall CTA (Visual State Triad — Empty/Unlit).
    await expect(
      page.getByRole("heading", { name: /Open the stacks|The shelves are still bare/ }),
    ).toBeVisible({ timeout: 30_000 });
  });
});
