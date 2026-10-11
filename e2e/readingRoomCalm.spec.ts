import { readFileSync } from "node:fs";
import { join } from "node:path";
import { expect, test, type Page } from "@playwright/test";
import { dismissWhatsNewIfPresent, loginAsOwner } from "./fixtures/auth";

const SCROLL_EPUB = readFileSync(join(process.cwd(), "e2e/fixtures/scroll-story.epub"));

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

const TALL_WORK = {
  ...WORK_DETAIL,
  work: {
    ...WORK_DETAIL.work,
    id: "work-tall",
    title: "The Tall Issue",
    description: Array.from({ length: 40 }, (_, index) => (
      `Contents line ${index + 1}. There is Foul Play on Mercury, and the page must stay reachable below the window.`
    )).join("\n\n"),
  },
  related: Array.from({ length: 8 }, (_, index) => ({
    id: `rel-${index}`,
    title: `Shelf neighbor ${index + 1}`,
    author: "A. Lamp",
    kind: "magazine",
  })),
};

async function mockTallWork(page: Page) {
  await page.route("**/api/works/work-tall", async (route) => {
    if (route.request().method() !== "GET") {
      await route.fallback();
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(TALL_WORK),
    });
  });
  await page.route("**/api/works/work-tall/download**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/epub+zip",
      headers: { "content-disposition": 'inline; filename="Tall.epub"' },
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

  test("reader fills the window when the work page is taller than the viewport", async ({ page }) => {
    await page.setViewportSize({ width: 1100, height: 520 });
    await mockTallWork(page);
    await page.goto("/works/work-tall?read=1");
    await dismissWhatsNewIfPresent(page);
    const reader = page.getByRole("dialog", { name: "The Tall Issue" });
    await expect(reader).toBeVisible({ timeout: 30_000 });
    const fit = await page.evaluate(() => {
      const readerEl = document.querySelector("[data-testid='reader']");
      const workEl = document.querySelector(".work-page");
      if (!(readerEl instanceof HTMLElement) || !(workEl instanceof HTMLElement)) {
        return null;
      }
      const readerBox = readerEl.getBoundingClientRect();
      const workBox = workEl.getBoundingClientRect();
      return {
        readerTop: readerBox.top,
        readerBottom: readerBox.bottom,
        readerHeight: readerBox.height,
        innerHeight: window.innerHeight,
        workHeight: workBox.height,
        pageTransform: getComputedStyle(workEl).transform,
      };
    });
    expect(fit).not.toBeNull();
    expect(fit!.workHeight).toBeGreaterThan(fit!.innerHeight + 80);
    expect(fit!.pageTransform).toBe("none");
    expect(fit!.readerTop).toBeLessThanOrEqual(1);
    expect(Math.abs(fit!.readerHeight - fit!.innerHeight)).toBeLessThanOrEqual(1);
    expect(Math.abs(fit!.readerBottom - fit!.innerHeight)).toBeLessThanOrEqual(1);
  });

  test("wheel scrolls the open story and Escape still closes", async ({ page }) => {
    await page.route("**/api/works/work-scroll", async (route) => {
      if (route.request().method() !== "GET") {
        await route.fallback();
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          ...WORK_DETAIL,
          work: { ...WORK_DETAIL.work, id: "work-scroll", title: "Astounding Stories", kind: "magazine" },
          files: [{ id: "story", filename: "Astounding.epub", kind: "magazine", size: SCROLL_EPUB.length, reading_room: true }],
        }),
      });
    });
    await page.route("**/api/works/work-scroll/download**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/epub+zip",
        headers: { "content-disposition": 'inline; filename="Astounding.epub"' },
        body: SCROLL_EPUB,
      });
    });
    await page.route("**/api/works/work-scroll/progress", async (route) => {
      await route.fulfill({ status: 200, contentType: "application/json", body: "{}" });
    });
    await page.setViewportSize({ width: 1100, height: 640 });
    await page.goto("/works/work-scroll?read=1");
    await dismissWhatsNewIfPresent(page);
    const reader = page.getByTestId("reader");
    await expect(reader).toBeVisible({ timeout: 30_000 });
    await expect.poll(async () => page.evaluate(() => {
      const view = document.querySelector("foliate-view") as HTMLElement & {
        renderer?: { getAttribute(name: string): string | null };
      };
      return view?.renderer?.getAttribute("flow") || "";
    }), { timeout: 20_000 }).toBe("scrolled");
    await expect.poll(async () => page.frames().length, { timeout: 20_000 }).toBeGreaterThan(1);
    const story = page.frames().find((frame) => frame !== page.mainFrame());
    expect(story).toBeTruthy();
    await expect(story!.getByText("Paragraph 1.")).toBeVisible({ timeout: 20_000 });
    const before = await page.evaluate(() => {
      const view = document.querySelector("foliate-view") as HTMLElement & {
        renderer?: { containerPosition: number };
      };
      return view.renderer?.containerPosition ?? 0;
    });
    const moved = await story!.evaluate(() => {
      const event = new WheelEvent("wheel", { deltaY: 480, deltaMode: 0, bubbles: true, cancelable: true });
      document.documentElement.dispatchEvent(event);
      return event.defaultPrevented;
    });
    expect(moved).toBe(true);
    await expect.poll(async () => page.evaluate(() => {
      const view = document.querySelector("foliate-view") as HTMLElement & {
        renderer?: { containerPosition: number };
      };
      return view.renderer?.containerPosition ?? 0;
    })).toBeGreaterThan(before + 100);
    await page.keyboard.press("Escape");
    await expect(reader).toBeHidden();
  });
});
