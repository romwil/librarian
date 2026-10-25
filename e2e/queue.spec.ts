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

  test("Open Review opens the linked hold slip", async ({ page }) => {
    await page.route("**/api/queue", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          jobs: [
            {
              id: "job-1",
              work_id: "slip-1",
              status: "review",
              title: "Three Weeks to Say Goodbye",
              review_reason: "low_confidence",
            },
          ],
        }),
      });
    });
    await page.route("**/api/review", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          works: [
            {
              id: "slip-1",
              kind: "book",
              title: "Three Weeks to Say Goodbye",
              author: "Box, C.J.",
              review_reason: "low_confidence",
              folder_path: "/data/media/newlib/Box, C.J_/Three Weeks to Say Goodbye (9989)",
              folder_diagnosis: {},
              actions: { recommended_motion: "apply", find_query: "Three Weeks to Say Goodbye Box, C.J." },
            },
          ],
          needs_review_count: 1,
        }),
      });
    });
    await page.route("**/api/settings/quiet-hours", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ quiet_hours_enabled: false, active_now: false }),
      });
    });

    await page.goto("/queue");
    await page.getByRole("link", { name: "Open Review" }).click();
    await expect(page).toHaveURL(/\/review\?work=slip-1/);
    await expect(page.getByLabel("Title")).toHaveValue("Three Weeks to Say Goodbye");
  });
});
