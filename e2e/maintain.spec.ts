import { expect, test } from "@playwright/test";
import { loginAsOwner } from "./fixtures/auth";

test.describe("Maintain", () => {
  test.beforeEach(async ({ page }) => {
    await loginAsOwner(page);
  });

  test("Maintain shows morning desk before the dock", async ({ page }) => {
    await page.goto("/maintain");
    await expect(page.getByRole("heading", { name: "Maintain" })).toBeVisible();
    const brief = page.getByTestId("morning-brief");
    await expect(brief).toBeVisible({ timeout: 30_000 });
    await expect(page.getByRole("heading", { name: "Tend these three." })).toBeVisible();
    await expect(page.getByText("Morning desk", { exact: true })).toBeVisible();
    await expect(page.getByTestId("morning-brief-presence")).toBeVisible();
    // Quiet house in mocked e2e — presence, not a zero KPI strip.
    await expect(page.getByTestId("morning-brief-presence")).toContainText(/clear|Tend|quiet/i);
    // Idle dock collapses entirely (no idle chip clutter).
    await expect(page.getByTestId("maintain-status-dock")).toHaveCount(0);
  });

  test("Maintain idle dock does not keep four job-status polls alive", async ({ page }) => {
    const jobsStatus: string[] = [];
    const fourFanOut: string[] = [];
    page.on("request", (req) => {
      const url = req.url();
      if (url.includes("/api/maintain/jobs/status")) {
        jobsStatus.push(url);
      }
      if (
        url.includes("/api/settings/scan/status") ||
        url.includes("/api/settings/enrich/status") ||
        url.includes("/api/ingest/status") ||
        url.includes("/api/review/reprocess-extra-files/status")
      ) {
        fourFanOut.push(url);
      }
    });

    await page.goto("/maintain");
    await expect(page.getByRole("heading", { name: "Maintain" })).toBeVisible();
    await expect(page.getByTestId("morning-brief")).toBeVisible({ timeout: 30_000 });
    // Dock collapsed when idle.
    await expect(page.getByTestId("maintain-status-dock")).toHaveCount(0);

    const jobsAfterPaint = jobsStatus.length;
    const fourAfterPaint = fourFanOut.length;
    // Probe once via multiplex; Wave 0 may one-shot individual endpoints for buttons.
    expect(jobsAfterPaint).toBeGreaterThanOrEqual(1);
    expect(jobsAfterPaint).toBeLessThanOrEqual(2);

    // Wait past a former live cadence — must not grow a four-endpoint idle fan-out.
    await page.waitForTimeout(2500);
    expect(jobsStatus.length).toBe(jobsAfterPaint);
    expect(fourFanOut.length).toBe(fourAfterPaint);
  });

  test("Maintain Add a volume offers Look first for ingest preview", async ({ page }) => {
    await page.goto("/maintain");
    await expect(page.getByRole("heading", { name: "Add a volume" })).toBeVisible({ timeout: 30_000 });
    await expect(page.getByTestId("maintain-ingest")).toBeVisible();
    // Scope to ingest — Calibre renormalize also ships a "Look first" CTA on Maintain.
    await expect(page.getByTestId("ingest-look-first")).toBeVisible();
    await expect(page.getByTestId("ingest-add")).toBeVisible();
    // Quiet map stays dark until Look first — presence ceremony, not a dump table.
    await expect(page.getByTestId("ingest-preview-map")).toHaveCount(0);
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

  test("Maintain Shelf health shows living pulse weather", async ({ page }) => {
    await page.goto("/maintain");
    await expect(page.getByTestId("maintain-shelf-health")).toBeVisible({ timeout: 30_000 });
    const pulse = page.getByTestId("shelf-health-pulse");
    await expect(pulse).toBeVisible();
    await expect(page.getByText("Shelf pulse", { exact: true })).toBeVisible();
    await expect(page.getByTestId("shelf-health-pulse-presence")).toBeVisible();
    // Quiet house — settled weather, not a numeric grade.
    await expect(page.getByTestId("shelf-health-pulse-presence")).toContainText(/settled|breeze|locked|stacks/i);
    await expect(pulse).not.toContainText(/%|scoreboard|KPI/i);
  });
});
