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

  test("Maintain Shelf health shows permission report and chown tip", async ({ page }) => {
    await page.goto("/maintain");
    await expect(page.getByRole("heading", { name: "Shelf health" })).toBeVisible({ timeout: 30_000 });
    await expect(page.getByTestId("maintain-shelf-health")).toBeVisible();
    await expect(page.getByTestId("maintain-shelf-health-report")).toBeVisible();
    await expect(page.getByTestId("maintain-shelf-health-chown-cmd")).toContainText("chown -R");
    await expect(page.getByTestId("maintain-scan")).toBeVisible();
    await expect(page.getByTestId("maintain-enrich")).toBeVisible();
  });
});
