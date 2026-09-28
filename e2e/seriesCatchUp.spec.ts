import { expect, test, type Page } from "@playwright/test";
import { dismissWhatsNewIfPresent, loginAsOwner } from "./fixtures/auth";

/** Hall payload carrying only the catch-up invitation (Sprint D1 lane FE-series). */
const CATCH_UP_HALL = {
  empty: false,
  tonight: { empty: true, continue: null, gap: null, surprise: null },
  continue: [],
  continue_listening: [],
  whats_new: [],
  favorites: [],
  areas: { books: [], magazines: [], comics: [], audiobooks: [], incoming_music: [] },
  gaps: [],
  kind_counts: {},
  celebrations: [],
  owner_ready: true,
  series_catch_up: {
    empty: false,
    series: [
      {
        id: "catchup:comic:Saga:",
        kind: "comic",
        series_name: "Saga",
        gap_type: "",
        author: "Gilt Pen",
        missing: ["3"],
        missing_count: 1,
        owned_count: 3,
        invitation: "One issue from a whole Saga.",
        next_gap: {
          id: "gap:comic:Saga:3",
          kind: "comic",
          series_name: "Saga",
          series_index: "3",
          missing_index: "3",
          title: "Saga 3",
          author: "Gilt Pen",
          provenance: "local",
        },
        ribbon: [
          { value: "1", state: "owned" },
          { value: "2", state: "owned" },
          { value: "3", state: "missing" },
          { value: "4", state: "owned" },
        ],
      },
      {
        id: "catchup:magazine:Linux Magazin:",
        kind: "magazine",
        series_name: "Linux Magazin",
        gap_type: "",
        author: "",
        missing: ["2026-09"],
        missing_count: 1,
        owned_count: 2,
        invitation: "One issue from a whole Linux Magazin.",
        next_gap: {
          id: "gap:magazine:Linux Magazin:2026-09",
          kind: "magazine",
          series_name: "Linux Magazin",
          series_index: "2026-09",
          missing_index: "2026-09",
          title: "Linux Magazin 2026-09",
          year: 2026,
          provenance: "local",
        },
        ribbon: [
          { value: "2026-08", state: "owned" },
          { value: "2026-09", state: "missing" },
          { value: "2026-10", state: "owned" },
        ],
      },
    ],
  },
};

const WHOLE_SHELF_HALL = {
  ...CATCH_UP_HALL,
  series_catch_up: { empty: true, series: [] },
};

async function mockHall(page: Page, body: unknown) {
  await page.route("**/api/hall", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(body),
    });
  });
}

test.describe("Series catch-up", () => {
  test.beforeEach(async ({ page }) => {
    await loginAsOwner(page);
  });

  test("invites the household to finish a nearly whole run", async ({ page }) => {
    await mockHall(page, CATCH_UP_HALL);
    await page.goto("/");
    await dismissWhatsNewIfPresent(page);

    const region = page.getByRole("region", { name: "Series catch-up" });
    await expect(region).toBeVisible({ timeout: 30_000 });
    await expect(page.getByRole("heading", { name: "A hole or two from whole" })).toBeVisible();
    await expect(region.getByText("One issue from a whole Saga.")).toBeVisible();
    await expect(region.getByText("One issue from a whole Linux Magazin.")).toBeVisible();
    await expect(region.getByText(/No hurry/)).toBeVisible();
    await expect(region.getByRole("img", { name: /On the shelf, missing 3/ })).toBeVisible();

    // Invitation, never a scoreboard.
    await expect(region.getByText(/\d+\s*\/\s*\d+/)).toHaveCount(0);
    await expect(region.getByText(/bagging/i)).toHaveCount(0);
  });

  test("owner CTA opens Find with the hole prefilled — no auto-queue", async ({ page }) => {
    await mockHall(page, CATCH_UP_HALL);
    await page.goto("/");
    await dismissWhatsNewIfPresent(page);

    const region = page.getByRole("region", { name: "Series catch-up" });
    await expect(region).toBeVisible({ timeout: 30_000 });
    const cta = region.getByRole("link", { name: "Find this hole" }).first();
    await expect(cta).toBeVisible();
    await cta.click();

    await expect(page).toHaveURL(/\/find\?/);
    const url = new URL(page.url());
    expect(url.searchParams.get("kind")).toBe("comic");
    expect(url.searchParams.get("series")).toBe("Saga");
    expect(url.searchParams.get("issue")).toBe("3");
  });

  test("stays hidden when the shelf is already whole", async ({ page }) => {
    await mockHall(page, WHOLE_SHELF_HALL);
    await page.goto("/");
    await dismissWhatsNewIfPresent(page);

    await expect(page.getByTestId("hall-shelves")).toBeVisible({ timeout: 30_000 });
    await expect(page.getByRole("region", { name: "Series catch-up" })).toHaveCount(0);
  });

  test("survives a malformed catch-up payload without breaking the Hall", async ({ page }) => {
    await mockHall(page, {
      ...CATCH_UP_HALL,
      series_catch_up: { empty: false, series: null },
    });
    await page.goto("/");
    await dismissWhatsNewIfPresent(page);

    await expect(page.getByRole("heading", { name: "What are you looking for?" })).toBeVisible();
    await expect(page.getByTestId("hall-shelves")).toBeVisible({ timeout: 30_000 });
    await expect(page.getByRole("region", { name: "Series catch-up" })).toHaveCount(0);
  });

  test("reduced-motion keeps the invitation readable and static", async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await mockHall(page, CATCH_UP_HALL);
    await page.goto("/");
    await dismissWhatsNewIfPresent(page);

    const region = page.getByRole("region", { name: "Series catch-up" });
    await expect(region).toBeVisible({ timeout: 30_000 });
    await expect(region.getByText("One issue from a whole Saga.")).toBeVisible();
    await expect(region.getByRole("link", { name: "Find this hole" }).first()).toBeVisible();

    const breathToken = await page.evaluate(() =>
      getComputedStyle(document.documentElement).getPropertyValue("--motion-breath").trim(),
    );
    expect(breathToken).toBe("1ms");

    // Nothing inside the invitation may still be breathing.
    const running = await region.evaluate((node) =>
      [node, ...node.querySelectorAll("*")].filter(
        (el) => getComputedStyle(el as Element).animationName !== "none",
      ).length,
    );
    expect(running).toBe(0);
  });
});
