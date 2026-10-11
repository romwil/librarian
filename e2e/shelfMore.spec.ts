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

  test("Hall catalog stays folded until More shelves", async ({ page }) => {
    await mockFoldedHall(page);
    await page.goto("/");
    await dismissWhatsNewIfPresent(page);

    await expect(page.getByRole("heading", { name: "Continue", exact: true })).toBeVisible({
      timeout: 30_000,
    });
    await expect(page.getByRole("button", { name: /Kept Volume/ })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Books" })).toBeHidden();
    await expect(page.getByRole("heading", { name: "Gaps as gifts" })).toBeHidden();
    await expect(page.getByRole("button", { name: /Bottom Catalog Book/ })).toBeHidden();

    await page.getByRole("button", { name: "More shelves" }).click();

    await expect(page.getByRole("heading", { name: "Books" })).toBeVisible();
    await expect(page.getByRole("button", { name: /Bottom Catalog Book/ })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Gaps as gifts" })).toBeVisible();
    await expect(page.getByRole("button", { name: /Missing Issue Gift/ })).toBeVisible();
  });

  test("Search keeps the local hit and folds the beyond door", async ({ page }) => {
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
          did_you_mean: [],
          forgave: false,
        }),
      });
    });
    await page.goto("/search?q=lamp");

    await expect(page.getByRole("heading", { name: "In the stacks" })).toBeVisible();
    await expect(page.getByRole("button", { name: /Lamp on the Shelf/ })).toBeVisible();
    await expect(page.getByRole("link", { name: "Find beyond the shelves" })).toBeHidden();

    await page.getByRole("button", { name: "More shelves" }).click();
    const beyond = page.getByRole("link", { name: "Find beyond the shelves" });
    await expect(beyond).toBeVisible();
    await expect(beyond).toHaveAttribute("href", /\/find\?/);
  });

  test("idle Search folds What's trending until More shelves", async ({ page }) => {
    await page.goto("/search");
    await expect(page.getByLabel("Search the stacks")).toBeVisible();
    await expect(page.getByRole("link", { name: "What's trending" })).toBeHidden();
    await page.getByRole("button", { name: "More shelves" }).click();
    await expect(page.getByRole("link", { name: "What's trending" })).toBeVisible();
  });
});
