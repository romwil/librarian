import { expect, test } from "@playwright/test";
import { dismissWhatsNewIfPresent, loginAsOwner } from "./fixtures/auth";

/** Minimal Hall payload with Tonight’s Shelf + Continue presence. */
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
  continue_listening: [],
  whats_new: [],
  favorites: [],
  areas: {
    books: [],
    magazines: [],
    comics: [],
    audiobooks: [],
    incoming_music: [],
  },
  gaps: [],
  kind_counts: {},
  celebrations: [],
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
      page.getByRole("heading", { name: /The shelves are waiting|The shelves are still bare/ }),
    ).toBeVisible({ timeout: 30_000 });
  });

  test("reduced-motion still shows Hall hero without motion crashes", async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.goto("/");
    await dismissWhatsNewIfPresent(page);
    await expect(page.getByRole("search")).toBeVisible();
    await expect(page.getByLabel("Search")).toBeVisible();
    await expect(
      page.getByRole("heading", { name: /The shelves are waiting|The shelves are still bare/ }),
    ).toBeVisible({ timeout: 30_000 });
  });

  test("Tonight’s Shelf alive — lamp presence and Continue rail", async ({ page }) => {
    await mockTonightHall(page);
    await page.goto("/");
    await dismissWhatsNewIfPresent(page);

    const shelf = page.getByRole("region", { name: "Tonight’s shelf" });
    await expect(shelf).toBeVisible({ timeout: 30_000 });
    await expect(page.getByRole("heading", { name: "Pick up where you left the lamp" })).toBeVisible();
    await expect(page.getByText("The room kept your place.")).toBeVisible();
    await expect(shelf.getByRole("button", { name: /The Lamp Novel/ })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Continue reading" })).toBeVisible();
  });

  test("Tonight’s Shelf respects reduced-motion", async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await mockTonightHall(page);
    await page.goto("/");
    await dismissWhatsNewIfPresent(page);

    await expect(page.getByRole("region", { name: "Tonight’s shelf" })).toBeVisible({
      timeout: 30_000,
    });
    await expect(page.getByRole("heading", { name: "Pick up where you left the lamp" })).toBeVisible();
    await expect(page.getByRole("button", { name: /Surprise Volume/ })).toBeVisible();
  });

  test("lamp rituals — period presence and welcome-back", async ({ page }) => {
    await mockTonightHall(page);
    await page.goto("/");
    await dismissWhatsNewIfPresent(page);

    await expect(page.getByRole("search")).toBeVisible();
    await expect(page.getByRole("region", { name: "Tonight’s shelf" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Continue reading" })).toBeVisible();
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

  test("skip link moves to the library main", async ({ page }) => {
    await page.goto("/");
    await dismissWhatsNewIfPresent(page);
    await page.getByRole("link", { name: "Skip to library" }).focus();
    await expect(page.getByRole("link", { name: "Skip to library" })).toBeFocused();
    await page.getByRole("link", { name: "Skip to library" }).press("Enter");
    await expect(page.getByRole("main")).toBeFocused();
  });
});
