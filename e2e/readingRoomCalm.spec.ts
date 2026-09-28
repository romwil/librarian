import { expect, test, type Page } from "@playwright/test";
import { dismissWhatsNewIfPresent, loginAsOwner } from "./fixtures/auth";

/** Work detail for Reading room calm (D3 reader lane). */
const WORK_DETAIL = {
  work: {
    id: "work-calm",
    title: "The Quiet Room",
    author: "A. Lamp",
    kind: "book",
    year: 2020,
    description: "A volume for long sessions.",
    review_state: "none",
  },
  files: [{ id: "f1", filename: "Quiet.epub", kind: "book", size: 800, reading_room: true }],
  file_count: 1,
  can_open: true,
  can_download: true,
  can_read: true,
  listen: { can_listen: false },
  komga: null,
  audiobook: null,
  favorite: false,
  related: [],
  progress: { fraction: 0.1, position: "" },
  ebook_convert: false,
  formats: [],
  series_ribbon: [],
  whispers: [],
};

async function mockWorkPage(page: Page) {
  await page.route("**/api/works/work-calm", async (route) => {
    if (route.request().method() !== "GET") {
      await route.fallback();
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(WORK_DETAIL),
    });
  });
  // Minimal EPUB bytes so the reader shell can open without a real volume.
  await page.route("**/api/works/work-calm/download**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/epub+zip",
      headers: { "content-disposition": 'inline; filename="Quiet.epub"' },
      body: Buffer.from("PK\x03\x04not-a-real-epub"),
    });
  });
}

test.describe("Reading room calm", () => {
  test.beforeEach(async ({ page }) => {
    await loginAsOwner(page);
  });

  test("Open reading room shows calm chrome without admin chrome", async ({ page }) => {
    await mockWorkPage(page);
    await page.goto("/works/work-calm?read=1");
    await dismissWhatsNewIfPresent(page);
    const reader = page.getByTestId("reader");
    await expect(reader).toBeVisible({ timeout: 30_000 });
    await expect(reader).toHaveAttribute("data-calm", "true");
    await expect(reader).toHaveClass(/reader-calm/);
    await expect(page.getByTestId("reader-head")).toBeVisible();
    await expect(page.getByTestId("reader-head").getByRole("heading", { name: "The Quiet Room" })).toBeVisible();
    await expect(page.getByTestId("reader-head").getByText("Reading room", { exact: true })).toBeVisible();
    // Top bar falls away while the volume is open.
    await expect(page.locator(".topbar")).toBeHidden();
  });

  test("reduced-motion keeps chrome visible (no idle dim)", async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await mockWorkPage(page);
    await page.goto("/works/work-calm?read=1");
    await dismissWhatsNewIfPresent(page);
    const reader = page.getByTestId("reader");
    await expect(reader).toBeVisible({ timeout: 30_000 });
    await expect(reader).toHaveClass(/reader-calm/);
    await expect(reader).not.toHaveClass(/is-chrome-dim/);
    await expect(page.getByTestId("reader-head")).toBeVisible();
    await expect(page.getByTestId("reader-close")).toBeVisible();
  });
});
