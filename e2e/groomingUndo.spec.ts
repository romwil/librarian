import { expect, test } from "@playwright/test";
import { loginAsOwner } from "./fixtures/auth";

test.describe("Safe undo grooming", () => {
  test.beforeEach(async ({ page }) => {
    await loginAsOwner(page);
  });

  test("Maintain shows safe undo calm when nothing to restore", async ({ page }) => {
    await page.goto("/maintain");
    await expect(page.getByRole("heading", { name: "Maintain" })).toBeVisible();
    const undo = page.getByTestId("grooming-undo");
    await expect(undo).toBeVisible({ timeout: 30_000 });
    await expect(page.getByText("Safe undo", { exact: true })).toBeVisible();
    await expect(page.getByTestId("grooming-undo-presence")).toBeVisible();
    await expect(page.getByTestId("grooming-undo-presence")).toContainText(/No recent|calm|undo|tend/i);
    // Quiet house — no restore CTA until a batch is recorded.
    await expect(page.getByTestId("grooming-undo-restore")).toHaveCount(0);
  });
});
