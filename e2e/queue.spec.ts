import { expect, test } from "@playwright/test";
import { loginAsOwner } from "./fixtures/auth";

test.describe("Queue", () => {
  test.beforeEach(async ({ page }) => {
    await loginAsOwner(page);
  });

  test("Queue loads empty asked-slip room without errors", async ({ page }) => {
    await page.goto("/queue");
    await expect(page.getByRole("heading", { name: "Queue" })).toBeVisible({ timeout: 30_000 });
    await expect(page.getByTestId("queue-loading")).toHaveCount(0, { timeout: 30_000 });
    // Fresh e2e DATA_DIR: empty queue copy (Visual State Triad — Empty).
    await expect(page.getByText(/Nothing in flight/i)).toBeVisible();
  });
});
