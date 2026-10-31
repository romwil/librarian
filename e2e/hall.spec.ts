import { expect, test } from "@playwright/test";
import { dismissWhatsNewIfPresent, loginAsOwner } from "./fixtures/auth";

/** Hall payload that still carries tonight and catch-up data the page must ignore. */
const TONIGHT_HALL = {
  empty: false,
  tonight: {
    empty: false,
    continue: {
      id: 101,
      title: "The Lamp Novel",
      author: "A. Reader",
      kind: "book",
      progress: 42,
      has_cover: false,
    },
    gap: null,
    surprise: {
      id: 202,
      title: "Surprise Volume",
      author: "B. Author",
      kind: "book",
      has_cover: false,
    },
  },
  continue: [
    {
      id: 101,
      title: "The Lamp Novel",
      author: "A. Reader",
      kind: "book",
      progress: 42,
      has_cover: false,
    },
  ],
  continue_listening: [
    {
      id: 301,
      title: "Night Radio",
      author: "C. Voice",
      kind: "audiobook",
      progress: 12,
      has_cover: false,
    },
  ],
  whats_new: [
    {
      id: 401,
      title: "Fresh Issue",
      author: "D. Editor",
      kind: "magazine",
      has_cover: false,
    },
  ],
  favorites: [
    {
      id: 501,
      title: "Kept Novel",
      author: "E. Keeper",
      kind: "book",
      has_cover: false,
    },
  ],
  series_catch_up: {
    empty: false,
    series: [
      {
        id: "catchup:comic:Saga:",
        series_name: "Saga",
        invitation: "One issue from a whole Saga.",
      },
    ],
  },
  areas: {
    books: [],
    magazines: [],
    comics: [],
    audiobooks: [],
    incoming_music: [],
  },
  gaps: [],
  kind_counts: { book: 2, audiobook: 1, magazine: 1 },
  named_shelves: [
    { id: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", name: "Bedside", work_count: 3 },
  ],
  owner_ready: true,
};

async function mockTonightHall(page: import("@playwright/test").Page) {
  await page.route("**/api/hall", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(TONIGHT_HALL),
    });
  });
}

test.describe("Hall", () => {
  test.beforeEach(async ({ page }) => {
    await loginAsOwner(page);
  });

  test("loads The Hall with shelves region", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Hall" })).toBeVisible();
    await expect(page.getByRole("search")).toBeVisible();
    await expect(page.getByLabel("Search")).toBeVisible();
    // Fresh e2e DATA_DIR: empty Hall CTA (Visual State Triad — Empty/Unlit).
    await expect(
      page.getByRole("heading", {
        name: /The shelves are waiting|No books on the shelves yet|The library is still being set up/,
      }),
    ).toBeVisible({ timeout: 30_000 });
  });

  test("reduced-motion still shows Hall hero without motion crashes", async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.goto("/");
    await dismissWhatsNewIfPresent(page);
    await expect(page.getByRole("search")).toBeVisible();
    await expect(page.getByLabel("Search")).toBeVisible();
    await expect(
      page.getByRole("heading", {
        name: /The shelves are waiting|No books on the shelves yet|The library is still being set up/,
      }),
    ).toBeVisible({ timeout: 30_000 });
  });

  test("Continue rails lead Hall and Tonight’s shelf stays off", async ({ page }) => {
    await mockTonightHall(page);
    await page.goto("/");
    await dismissWhatsNewIfPresent(page);

    await expect(page.getByRole("heading", { name: "Continue listening" })).toBeVisible({
      timeout: 30_000,
    });
    await expect(page.getByRole("heading", { name: "Continue reading" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Recently added" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Favorites" })).toBeVisible();
    await expect(page.getByRole("navigation", { name: "Shelves" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Books · 2" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Bedside · 3" })).toBeVisible();
    await expect(page.getByRole("button", { name: /^The Lamp Novel/ })).toBeVisible();
    await expect(page.getByRole("button", { name: /^Night Radio/ })).toBeVisible();
    await expect(page.getByRole("region", { name: "Tonight’s shelf" })).toHaveCount(0);
    await expect(page.getByRole("heading", { name: "Pick up where you left the lamp" })).toHaveCount(0);
    await expect(page.getByRole("region", { name: "Series catch-up" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: /Surprise Volume/ })).toHaveCount(0);

    const top = async (name: string) =>
      (await page.getByRole("heading", { name, exact: true }).boundingBox())?.y ?? 0;
    expect(await top("Continue listening")).toBeLessThan(await top("Continue reading"));
    expect(await top("Continue reading")).toBeLessThan(await top("Recently added"));
    expect(await top("Recently added")).toBeLessThan(await top("Favorites"));
  });

  test("reduced-motion still shows Continue without Tonight’s shelf", async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await mockTonightHall(page);
    await page.goto("/");
    await dismissWhatsNewIfPresent(page);

    await expect(page.getByRole("heading", { name: "Continue reading" })).toBeVisible({
      timeout: 30_000,
    });
    await expect(page.getByRole("region", { name: "Tonight’s shelf" })).toHaveCount(0);
    await expect(page.getByRole("heading", { name: "Pick up where you left the lamp" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: /Surprise Volume/ })).toHaveCount(0);
  });

  test("lamp rituals — search and Continue without Tonight’s shelf", async ({ page }) => {
    await mockTonightHall(page);
    await page.goto("/");
    await dismissWhatsNewIfPresent(page);

    await expect(page.getByRole("search")).toBeVisible();
    await expect(page.getByRole("heading", { name: "Continue reading" })).toBeVisible();
    await expect(page.getByRole("region", { name: "Tonight’s shelf" })).toHaveCount(0);
  });

  test("Hall search opens Search results", async ({ page }) => {
    await page.route("**/api/search**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          q: "dune",
          local: [],
          beyond: [],
          public_domain: [],
          did_you_mean: [],
          forgave: false,
        }),
      });
    });
    await page.goto("/");
    await dismissWhatsNewIfPresent(page);
    await page.getByRole("search").getByLabel("Search").fill("dune");
    await page.getByRole("search").getByRole("button", { name: "Search" }).click();
    await expect(page).toHaveURL(/\/search\?q=dune/);
    await expect(page.getByRole("heading", { name: "On the shelf" })).toBeVisible();
  });

  test("skip link jumps keyboard focus to main", async ({ page }) => {
    await page.goto("/");
    await dismissWhatsNewIfPresent(page);
    await expect(page.getByRole("heading", { name: "Hall" })).toBeVisible();
    const skip = page.getByRole("link", { name: "Skip to content" });
    await skip.focus();
    await expect(skip).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(page.locator("#main")).toBeFocused();
  });
});
