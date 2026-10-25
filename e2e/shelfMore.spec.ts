import { expect, test, type Page } from "@playwright/test";
import { dismissWhatsNewIfPresent, loginAsOwner } from "./fixtures/auth";

const FOLDED_HALL = {
  empty: false,
  tonight: { empty: true, continue: null, gap: null, surprise: null },
  continue: [
    {
      id: 1,
      title: "Kept Volume",
      author: "A. Reader",
      kind: "book",
      has_cover: false,
    },
  ],
  continue_listening: [],
  whats_new: [],
  favorites: [],
  named_shelves: [],
  areas: {
    books: [
      {
        id: 9,
        title: "Bottom Catalog Book",
        author: "Z. Shelf",
        kind: "book",
        has_cover: false,
      },
    ],
    magazines: [],
    comics: [],
    audiobooks: [],
    incoming_music: [],
  },
  gaps: [
    {
      id: "g1",
      title: "Missing Issue Gift",
      author: "Various",
      kind: "magazine",
    },
  ],
  gaps_pending: false,
  series_catch_up: { empty: true, series: [] },
  kind_counts: { book: 1 },
  celebrations: [],
  owner_ready: true,
};

async function mockFoldedHall(page: Page) {
  await page.route("**/api/hall", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(FOLDED_HALL),
    });
  });
  await page.route("**/api/gaps/local", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        gaps: FOLDED_HALL.gaps,
        gaps_pending: false,
        series_catch_up: { empty: true, series: [] },
      }),
    });
  });
}

test.describe("More shelves", () => {
  test.beforeEach(async ({ page }) => {
    await loginAsOwner(page);
  });

  test("Hall keeps personalized rails and omits the catalog list", async ({ page }) => {
    await mockFoldedHall(page);
    await page.goto("/");
    await dismissWhatsNewIfPresent(page);

    await expect(page.getByRole("heading", { name: "Continue reading" })).toBeVisible({
      timeout: 30_000,
    });
    await expect(page.getByRole("button", { name: "Kept Volume", exact: true })).toBeVisible();
    await expect(page.getByRole("search")).toBeVisible();
    await expect(page.getByRole("button", { name: "All", exact: true })).toHaveCount(0);
    await expect(page.getByRole("heading", { name: "Name a shelf" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "More shelves" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: /Bottom Catalog Book/ })).toHaveCount(0);
  });

  test("Search keeps the local hit then Beyond", async ({ page }) => {
    await page.route("**/api/search**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          q: "lamp",
          local: [
            {
              id: 3,
              title: "Lamp on the Shelf",
              author: "A. Reader",
              kind: "book",
              has_cover: false,
            },
          ],
          beyond: [],
          public_domain: [],
          did_you_mean: [],
          forgave: false,
        }),
      });
    });
    await page.goto("/search?q=lamp");

    await expect(page.getByRole("heading", { name: "On the shelf" })).toBeVisible();
    await expect(page.getByRole("button", { name: /Lamp on the Shelf/ })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Beyond" })).toBeVisible();
    await expect(page.getByRole("button", { name: "More shelves" })).toHaveCount(0);
  });

  test("idle Search keeps a quiet New & noted door", async ({ page }) => {
    await page.goto("/search");
    await expect(page.getByRole("search").getByLabel("Search")).toBeVisible();
    await expect(page.getByRole("link", { name: "Trending books" })).toBeVisible();
    await expect(page.getByRole("link", { name: "New & noted" })).toBeVisible();
    await expect(page.getByRole("button", { name: "More shelves" })).toHaveCount(0);
  });
});
