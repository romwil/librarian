import { expect, test } from "@playwright/test";
import { loginAsOwner } from "./fixtures/auth";

test.describe("Maintain", () => {
  test.beforeEach(async ({ page }) => {
    await loginAsOwner(page);
  });

  test("Maintain shows telemetry dock idle copy", async ({ page }) => {
    await page.goto("/maintain");
    await expect(page.getByRole("heading", { name: "Maintain" })).toBeVisible();
    await expect(page.getByTestId("maintain-status-idle")).toBeVisible({ timeout: 30_000 });
    await expect(page.getByText(/No scan, enrich, shelving, or clear jobs running/i)).toBeVisible();
    // Embedded Add-to-library must not duplicate shelving meters on Maintain.
    await expect(page.getByTestId("ingest-progress")).toHaveCount(0);
  });
});
