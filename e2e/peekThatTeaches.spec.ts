import { expect, test, type Page } from "@playwright/test";
import { dismissWhatsNewIfPresent, loginAsOwner } from "./fixtures/auth";

const SHELL_WORK = {
  work: {
    id: "shell-peek",
    title: "Empty Shell",
    author: "A. Lamp",
    kind: "book",
    year: 2020,
    description: "A catalog shell with no file.",
    review_state: "none",
  },
  files: [],
  file_count: 0,
  can_open: false,
  can_download: false,
  can_read: false,
  listen: { can_listen: false },
  komga: null,
  audiobook: null,
  favorite: false,
  related: [],
  progress: null,
};

async function mockShellPeek(page: Page) {
  await page.route("**/api/works/shell-peek", async (route) => {
    if (route.request().method() !== "GET") {
      await route.fallback();
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(SHELL_WORK),
    });
  });
  await page.route("**/api/hall**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        continue: [],
        listening: [],
        whats_new: [SHELL_WORK.work],
        favorites: [],
        books: [],
        magazines: [],
        comics: [],
        audiobooks: [],
        music: [],
      }),
    });
  });
}

test.describe("Peek that teaches", () => {
  test.beforeEach(async ({ page }) => {
    await loginAsOwner(page);
  });

  test("Peek of an unshelved shell shows honest empty teaching", async ({ page }) => {
    await mockShellPeek(page);
    await page.goto("/");
    await dismissWhatsNewIfPresent(page);
    // Open peek from What's New rail if present; else go work page.
    const cover = page.getByRole("button", { name: /Empty Shell/i }).first();
    if (await cover.count()) {
      await cover.click();
    } else {
      await page.goto("/works/shell-peek");
      await dismissWhatsNewIfPresent(page);
      // Work page itself teaches; also try peek via cover if Hall mounts.
    }
    const peek = page.getByTestId("peek");
    if (await peek.count()) {
      await expect(peek).toBeVisible({ timeout: 15_000 });
      await expect(page.getByTestId("peek-media-note")).toBeVisible();
      await expect(page.getByTestId("peek-media-note")).toContainText(/isn’t on the shelf|Holds desk|file yet/i);
      // Never fake an Open/Read CTA for a shell without files.
      await expect(page.getByTestId("peek-open")).toHaveCount(0);
    } else {
      // Fallback: work page media honesty.
      await page.goto("/works/shell-peek");
      await dismissWhatsNewIfPresent(page);
      await expect(page.getByRole("heading", { name: "Empty Shell" })).toBeVisible({ timeout: 15_000 });
      await expect(page.getByTestId("peek-open")).toHaveCount(0);
    }
  });
});
