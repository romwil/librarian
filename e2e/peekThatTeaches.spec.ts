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
    const note = /isn.t on the shelf|file yet/i;
    const cover = page.getByRole("button", { name: /^Empty Shell/ });
    const onHall = await cover
      .waitFor({ state: "visible", timeout: 15_000 })
      .then(() => true)
      .catch(() => false);
    if (onHall) {
      await cover.click();
      const peek = page.getByRole("dialog", { name: "Empty Shell" });
      await expect(peek).toBeVisible({ timeout: 15_000 });
      await expect(peek.getByText(note)).toBeVisible();
      // A shell has no file, so the primary peek CTA is not Read/Download. Favorite is in the grip.
      await expect(peek.getByTestId("peek-open")).toHaveCount(0);
      await expect(peek.getByTestId("peek-listen")).toHaveCount(0);
      await expect(peek.getByRole("button", { name: "Favorite", exact: true })).toHaveCount(0);
      const grip = peek.getByRole("button", { name: "Actions for Empty Shell", exact: true });
      await grip.focus();
      await expect(grip).toBeFocused();
      await page.keyboard.press("Enter");
      const menu = page.getByRole("menu", { name: "Actions for Empty Shell", exact: true });
      const favorite = menu.getByRole("button", { name: "Favorite", exact: true });
      await expect(favorite).toBeVisible();
      await favorite.focus();
      await expect(favorite).toBeFocused();
      await expect(menu.getByRole("link", { name: "Download", exact: true })).toHaveCount(0);
      return;
    }
    await page.goto("/works/shell-peek");
    await dismissWhatsNewIfPresent(page);
    await expect(page.getByRole("heading", { name: "Empty Shell" })).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText(note)).toBeVisible();
    await expect(page.getByRole("button", { name: "Read", exact: true })).toHaveCount(0);
    await expect(page.getByRole("link", { name: "Download", exact: true })).toHaveCount(0);
    const grip = page.getByRole("button", { name: "Actions for Empty Shell", exact: true });
    await grip.click();
    const menu = page.getByRole("menu", { name: "Actions for Empty Shell", exact: true });
    await expect(menu.getByRole("button", { name: "Favorite", exact: true })).toBeVisible();
    await expect(menu.getByRole("link", { name: "Download", exact: true })).toHaveCount(0);
  });
});
