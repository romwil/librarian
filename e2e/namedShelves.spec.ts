import { expect, test } from "@playwright/test";
import { dismissWhatsNewIfPresent, loginAsOwner } from "./fixtures/auth";

test.describe("Named household shelves", () => {
  test.beforeEach(async ({ page }) => {
    await loginAsOwner(page);
    await dismissWhatsNewIfPresent(page);
  });

  test("Hall shows named shelves create chrome", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByTestId("hall-shelves")).toBeVisible({ timeout: 30_000 });
    await expect(page.getByTestId("named-shelves")).toBeVisible({ timeout: 30_000 });
    await expect(page.getByRole("heading", { name: "Named shelves" })).toBeVisible();
    await expect(page.getByTestId("named-shelves-presence")).toBeVisible();
    await expect(page.getByTestId("named-shelves-create")).toBeVisible();
  });
});
