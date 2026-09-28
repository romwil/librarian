import { expect, test } from "@playwright/test";
import { loginAsOwner } from "./fixtures/auth";

test.describe("Calibre re-normalize", () => {
  test.beforeEach(async ({ page }) => {
    await loginAsOwner(page);
  });

  test("Maintain shows Look first Calibre ritual", async ({ page }) => {
    await page.goto("/maintain");
    await expect(page.getByTestId("calibre-renormalize")).toBeVisible({ timeout: 30_000 });
    await expect(page.getByRole("heading", { name: "Re-normalize" })).toBeVisible();
    await expect(page.getByTestId("calibre-renormalize-look")).toBeVisible();
    await page.getByTestId("calibre-renormalize-look").click();
    await expect(page.getByTestId("calibre-renormalize-presence")).toBeVisible();
  });
});
