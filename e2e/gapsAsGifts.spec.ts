import { expect, test } from "@playwright/test";
import { dismissWhatsNewIfPresent, loginAsOwner } from "./fixtures/auth";

test.describe("Gaps as gifts", () => {
  test.beforeEach(async ({ page }) => {
    await loginAsOwner(page);
    await dismissWhatsNewIfPresent(page);
  });

  test("Hall gaps rail speaks as gifts", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByTestId("hall-shelves")).toBeVisible({ timeout: 30_000 });
    await expect(page.getByRole("search")).toBeVisible();
    await expect(page.getByRole("button", { name: "More shelves" })).toHaveCount(0);
  });
});
