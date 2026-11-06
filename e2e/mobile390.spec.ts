import { expect, test } from "@playwright/test";
import { dismissWhatsNewIfPresent, loginAsOwner } from "./fixtures/auth";

/**
 * UX-007 — authored 390px proof for Hall / Search / Sorting + mobile tab bar.
 * Mocked e2e on :8794; not a substitute for live Automat visual QA.
 */
const PHONE = { width: 390, height: 844 };

async function assertNoTwoAxisPageScroll(page: import("@playwright/test").Page) {
  const fit = await page.evaluate(() => {
    const doc = document.documentElement;
    return {
      scrollWidth: doc.scrollWidth,
      clientWidth: doc.clientWidth,
      innerWidth: window.innerWidth,
    };
  });
  expect(fit.scrollWidth).toBeLessThanOrEqual(fit.clientWidth + 1);
  expect(fit.scrollWidth).toBeLessThanOrEqual(fit.innerWidth + 1);
}

async function assertMobileTabBarUsable(page: import("@playwright/test").Page) {
  const mobile = page.getByRole("navigation", { name: "Mobile" });
  await expect(mobile).toBeVisible();
  await expect(mobile.getByRole("link", { name: "Hall", exact: true })).toBeVisible();
  await expect(mobile.getByRole("link", { name: "Search", exact: true })).toBeVisible();
  await expect(mobile.getByRole("link", { name: "Favorites", exact: true })).toBeVisible();
  await expect(mobile.getByRole("link", { name: /Desk/ })).toBeVisible();
  await expect(mobile.getByRole("link", { name: "You", exact: true })).toBeVisible();
  const box = await mobile.boundingBox();
  expect(box).toBeTruthy();
  expect(box!.width).toBeLessThanOrEqual(PHONE.width + 1);
  expect(box!.height).toBeGreaterThanOrEqual(44);
}

test.describe("Mobile 390 proof (UX-007)", () => {
  test.beforeEach(async ({ page }) => {
    await page.setViewportSize(PHONE);
    await loginAsOwner(page);
  });

  test("Hall tab bar usable without horizontal page scroll", async ({ page }) => {
    await page.goto("/");
    await dismissWhatsNewIfPresent(page);
    await expect(page.getByRole("link", { name: "Librarian" })).toBeVisible();
    await assertMobileTabBarUsable(page);
    await assertNoTwoAxisPageScroll(page);
  });

  test("Search tab bar usable without horizontal page scroll", async ({ page }) => {
    await page.goto("/search");
    await dismissWhatsNewIfPresent(page);
    await expect(page.getByRole("searchbox").or(page.getByLabel(/search/i)).first()).toBeVisible({
      timeout: 30_000,
    });
    await assertMobileTabBarUsable(page);
    await assertNoTwoAxisPageScroll(page);
  });

  test("Sorting selected actions stay in view at 390", async ({ page }) => {
    const slips = Array.from({ length: 3 }, (_, i) => ({
      id: `m390-${i}`,
      title: `Phone Slip ${i} with a deliberately long path that should wrap`,
      kind: "book",
      author: "Ann Author",
      review_reason: "low_confidence",
      effective_reason: "low_confidence",
      path: `/data/books/Very/Long/Author/Name/Phone Slip ${i}/file.epub`,
      folder_diagnosis: { path_clear: true },
      actions: { recommended_motion: "apply", find_query: `Phone Slip ${i}` },
    }));
    await page.route(/\/api\/review(\?|$)/, async (route) => {
      if (route.request().method() !== "GET") {
        await route.continue();
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          works: slips,
          llm_configured: false,
          extra_files_count: 0,
          needs_review_count: 3,
          counts_by_reason: { low_confidence: 3 },
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
    await page.route("**/api/review/suggest-batch/status", async (route) => {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "idle" }) });
    });
    await page.route("**/api/review/bad-release-migration/status", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ status: "idle" }),
      });
    });
    await page.route("**/api/auth/me", async (route) => {
      if (route.request().method() !== "GET") {
        await route.continue();
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          user: { id: "e2e-owner", display_name: "E2E Owner", role: "owner", username: "e2e-owner" },
          review_count: 3,
          inbox_unread: 0,
        }),
      });
    });

    await page.goto("/review");
    await dismissWhatsNewIfPresent(page);
    await assertMobileTabBarUsable(page);
    const deskTab = page.getByTestId("desk-tab");
    await expect(deskTab).toBeVisible();
    await expect(deskTab.getByTestId("desk-badge-dot")).toBeVisible();
    await expect(deskTab.getByTestId("desk-nav-label")).toHaveAttribute("data-badge-mode", "quiet");
    const firstSlip = page.getByRole("listitem").filter({ hasText: "Phone Slip 0" }).first();
    await expect(firstSlip).toBeVisible({ timeout: 30_000 });
    await firstSlip.click();
    const apply = page.getByRole("button", { name: /^Apply$/i }).first();
    await expect(apply).toBeVisible();
    await apply.scrollIntoViewIfNeeded();
    const applyBox = await apply.boundingBox();
    expect(applyBox).toBeTruthy();
    // Above the fixed mobile tab bar (clearance ~48px + home indicator).
    expect(applyBox!.y + applyBox!.height).toBeLessThanOrEqual(PHONE.height - 40);
    expect(applyBox!.x + applyBox!.width).toBeLessThanOrEqual(PHONE.width + 1);
    await assertNoTwoAxisPageScroll(page);
  });
});
