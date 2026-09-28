import { expect, test } from "@playwright/test";
import { loginAsOwner } from "./fixtures/auth";

test.describe("Indexer scorecard", () => {
  test.beforeEach(async ({ page }) => {
    await loginAsOwner(page);
  });

  test("Maintain shows Find lanterns scorecard", async ({ page }) => {
    await page.goto("/maintain");
    await expect(page.getByRole("heading", { name: "Maintain" })).toBeVisible();
    const card = page.getByTestId("indexer-scorecard");
    await expect(card).toBeVisible({ timeout: 30_000 });
    await expect(page.getByRole("heading", { name: "Indexer scorecard" })).toBeVisible();
    await expect(page.getByText("Find lanterns", { exact: true })).toBeVisible();
    await expect(page.getByTestId("indexer-scorecard-presence")).toBeVisible();
    // Quiet house — presence, not a latency KPI strip.
    await expect(page.getByTestId("indexer-scorecard-presence")).toContainText(/lantern|Find|mute|steady|wait/i);
    await expect(page.getByTestId("indexer-lantern").first()).toBeVisible();
    // Mute only when a host is configured — e2e may have an idle primary lantern.
    await expect(page.getByTestId("indexer-lantern").first()).toContainText(/NZBFinder|Indexer|spoken|muted|steady|dark|flicker/i);
  });
});
