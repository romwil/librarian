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
    // Fresh e2e DATA_DIR: empty actionable default (PRD-011).
    await expect(page.getByTestId("queue-view-actionable")).toHaveAttribute("aria-pressed", "true");
    await expect(page.getByTestId("queue-empty")).toBeVisible();
    await expect(page.getByText(/Nothing needs a decision/i)).toBeVisible();
  });

  test("Open Sorting opens the linked slip", async ({ page }) => {
    await page.route("**/api/queue**", async (route) => {
      if (route.request().method() !== "GET") {
        await route.continue();
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          view: "actionable",
          counts: { actionable: 1, active: 0, history: 0, all: 1 },
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
    await page.route("**/api/queue**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          view: "actionable",
          counts: { actionable: 2, active: 0, history: 0, all: 2 },
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

  test("default view hides Arrived; bulk dismiss confirms count", async ({ page }) => {
    const dismissed: string[] = [];
    await page.route("**/api/queue**", async (route) => {
      const url = new URL(route.request().url());
      if (route.request().method() !== "GET") {
        await route.continue();
        return;
      }
      const view = url.searchParams.get("view") || "actionable";
      const allJobs = [
        {
          id: "job-asked",
          status: "asked",
          title: "Confirm me",
        },
        {
          id: "job-fail",
          status: "failed",
          title: "A miss",
          error: "nzb gone",
        },
        {
          id: "job-arrived",
          status: "organized",
          title: "Already home",
        },
        {
          id: "job-active",
          status: "downloading",
          title: "In flight",
        },
      ];
      const byView: Record<string, string[]> = {
        actionable: ["asked", "failed", "review"],
        active: ["queued", "downloading", "extracting", "identifying"],
        history: ["organized"],
        all: allJobs.map((j) => j.status),
      };
      const allowed = new Set(byView[view] || byView.actionable);
      const jobs = allJobs.filter((j) => allowed.has(j.status));
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          view,
          counts: { actionable: 2, active: 1, history: 1, all: 4 },
          jobs,
        }),
      });
    });
    await page.route("**/api/queue/*/dismiss", async (route) => {
      const id = route.request().url().split("/").slice(-2)[0];
      dismissed.push(id);
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ job: { id, status: "skipped" } }),
      });
    });

    await page.goto("/queue");
    await dismissWhatsNewIfPresent(page);
    await expect(page.getByTestId("queue-view-actionable")).toHaveAttribute("aria-pressed", "true");
    await expect(page.getByTestId("queue-job")).toHaveCount(2);
    await expect(page.getByText("Already home")).toHaveCount(0);
    await expect(page.getByText("In flight")).toHaveCount(0);

    await page.getByTestId("queue-view-history").click();
    await expect(page.getByText("Already home")).toBeVisible();
    await expect(page.getByTestId("queue-bulk-dismiss")).toBeVisible();
    await page.getByTestId("queue-bulk-dismiss").click();
    await expect(page.getByTestId("queue-bulk-dismiss-dialog")).toBeVisible();
    await expect(page.getByTestId("queue-bulk-dismiss-count")).toContainText("1 Arrived");
    await expect(page.getByTestId("queue-bulk-dismiss-undo")).toContainText(/no Safe undo/i);
    await page.getByTestId("queue-bulk-dismiss-confirm").click();
    await expect.poll(() => dismissed).toEqual(["job-arrived"]);
  });
});
