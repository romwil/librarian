import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { dismissWhatsNewIfPresent, loginAsOwner } from "./fixtures/auth";

const WORK = {
  work: {
    id: "seed-1",
    title: "Seeded Volume",
    author: "A. Reader",
    kind: "book",
    year: 1965,
    review_state: "",
  },
  can_download: false,
  can_read: false,
  files: [],
  file_count: 0,
  favorite: false,
  listen: { can_listen: false },
};

async function setTheme(page: Page, name: "Lights Up" | "Lights Down") {
  const testId = name === "Lights Up" ? "profile-theme-lights_up" : "profile-theme-lights_down";
  await page.getByTestId("profile-menu-trigger").click();
  await page.getByTestId(testId).click();
  await page.locator(".room").evaluate((el) => {
    el.setAttribute("data-ambient", "off");
  });
  await page.keyboard.press("Escape");
}

/** Let page-settle / soft-enter fades finish: axe samples colors mid-fade otherwise. */
async function settleMotion(page: Page) {
  await page.evaluate(() =>
    Promise.all(
      document
        .getAnimations()
        .filter((animation) => Number.isFinite(animation.effect?.getComputedTiming().endTime))
        .map((animation) => animation.finished.catch(() => undefined)),
    ),
  );
}

async function assertAxe(page: Page) {
  await settleMotion(page);
  const results = await new AxeBuilder({ page }).analyze();
  const summary = results.violations
    .map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join("; ")}`)
    .join("\n");
  expect(results.violations, summary).toEqual([]);
}

test.describe("axe-core", () => {
  test("login Lights Up", async ({ page }) => {
    await page.goto("/login");
    await expect(page.getByRole("heading", { name: "The Reading Room" })).toBeVisible();
    await assertAxe(page);
  });

  for (const theme of ["Lights Up", "Lights Down"] as const) {
    test.describe(theme, () => {
      test.beforeEach(async ({ page }) => {
        await loginAsOwner(page);
        await setTheme(page, theme);
      });

      test("Hall", async ({ page }) => {
        await page.goto("/");
        await dismissWhatsNewIfPresent(page);
        await expect(page.getByRole("heading", { name: "Hall" })).toBeVisible();
        await assertAxe(page);
      });

      test("Search", async ({ page }) => {
        await page.goto("/search");
        await expect(page.getByRole("search")).toBeVisible();
        await assertAxe(page);
      });

      test("Work", async ({ page }) => {
        await page.route("**/api/works/seed-1", async (route) => {
          await route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify(WORK),
          });
        });
        await page.goto("/works/seed-1");
        await expect(page.getByRole("heading", { name: "Seeded Volume" })).toBeVisible();
        await assertAxe(page);
      });

      test("Sorting", async ({ page }) => {
        await page.goto("/review");
        await expect(page.getByRole("heading", { name: "Sorting", exact: true })).toBeVisible();
        await assertAxe(page);
      });

      test("Settings", async ({ page }) => {
        await page.goto("/settings");
        await expect(page.getByRole("heading", { name: /Settings/i })).toBeVisible();
        await assertAxe(page);
      });

      test("Library card", async ({ page }) => {
        await page.goto("/card");
        await expect(page.getByRole("heading", { name: "Your library" })).toBeVisible();
        await assertAxe(page);
      });
    });
  }
});
