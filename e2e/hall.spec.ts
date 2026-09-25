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
    await expect(page.getByText("The Hall").first()).toBeVisible();
    await expect(page.getByRole("heading", { name: "What are you looking for?" })).toBeVisible();
    // Fresh e2e DATA_DIR: empty Hall CTA (Visual State Triad — Empty/Unlit).
    await expect(
      page.getByRole("heading", { name: /Open the stacks|The shelves are still bare/ }),
    ).toBeVisible({ timeout: 30_000 });
  });

  test("reduced-motion still shows Hall hero without motion crashes", async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.goto("/");
    await dismissWhatsNewIfPresent(page);
    await expect(page.getByRole("heading", { name: "What are you looking for?" })).toBeVisible();
    await expect(page.getByLabel("Search the stacks")).toBeVisible();
    await expect(
      page.getByRole("heading", { name: /Open the stacks|The shelves are still bare/ }),
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
    await expect(page.getByRole("heading", { name: "Continue", exact: true })).toBeVisible();
    await expect(page.getByText("Volumes waiting under the lamp")).toBeVisible();
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
});
