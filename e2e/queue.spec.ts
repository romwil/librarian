import { expect, test } from "@playwright/test";
import { dismissWhatsNewIfPresent, loginAsOwner } from "./fixtures/auth";

test.describe("Queue", () => {
  test.beforeEach(async ({ page }) => {
    await loginAsOwner(page);
  });

  test("Queue loads empty asked-slip room without errors", async ({ page }) => {
    await page.goto("/queue");
    await expect(page.getByRole("heading", { name: "Downloads" })).toBeVisible({ timeout: 30_000 });
    await expect(page.getByTestId("queue-loading")).toHaveCount(0, { timeout: 30_000 });
    // Fresh e2e DATA_DIR: empty queue copy (Visual State Triad — Empty).
    await expect(page.getByText(/Nothing in flight/i)).toBeVisible();
  });

  test("Open Sorting opens the linked slip", async ({ page }) => {
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
    await page.route(
      (url) => new URL(url).pathname === "/api/review",
      async (route) => {
        if (route.request().method() !== "GET") {
          await route.continue();
          return;
        }
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
      },
    );
    await page.route("**/api/settings/quiet-hours", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ quiet_hours_enabled: false, active_now: false }),
      });
    });

    await page.goto("/queue");
    await dismissWhatsNewIfPresent(page);
    await page.getByRole("link", { name: "Open Sorting" }).click();
    await expect(page).toHaveURL(/\/review\?work=slip-1/);
    await expect(page.getByRole("heading", { name: "Sorting", exact: true })).toBeVisible();
    await expect(page.getByText("Three Weeks to Say Goodbye", { exact: true })).toBeVisible();
  });

  test("failed jobs are actionable and paths sit behind Details", async ({ page }) => {
    await page.route("**/api/queue", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          jobs: [
            {
              id: "job-fail",
              status: "failed",
              title: "A miss",
              error: "nzb gone",
              storage_path: "/data/complete/A.miss.epub",
            },
            {
              id: "job-review",
              work_id: "slip-1",
              status: "review",
              title: "Needs a sort",
              review_reason: "low_confidence",
            },
          ],
        }),
      });
    });
    const retried: string[] = [];
    await page.route("**/api/queue/job-fail/retry", async (route) => {
      retried.push("retry");
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ job: { id: "job-fail", status: "asked", title: "A miss" } }),
      });
    });
    await page.setViewportSize({ width: 320, height: 720 });
    await page.goto("/queue");
    await dismissWhatsNewIfPresent(page);
    const jobs = page.getByTestId("queue-job");
    await expect(jobs.first()).toHaveAttribute("data-status", "review");
    await expect(page.getByTestId("queue-needs-you-help")).toBeVisible();
    await expect(page.getByRole("button", { name: "Try again" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Dismiss" }).first()).toBeVisible();
    await expect(page.getByTestId("queue-ops-detail")).toBeHidden();
    await page.getByText("Details").click();
    await expect(page.getByTestId("queue-ops-detail")).toBeVisible();
    await expect(page.getByTestId("queue-ops-detail")).toHaveText("/data/complete/A.miss.epub");
    const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
    expect(scrollWidth).toBeLessThanOrEqual(320 + 1);
    await page.getByRole("button", { name: "Try again" }).click();
    expect(retried).toEqual(["retry"]);
  });
});
