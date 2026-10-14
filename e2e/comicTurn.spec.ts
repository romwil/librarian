import { readFileSync } from "node:fs";
import { join } from "node:path";
import { expect, test } from "@playwright/test";
import { dismissWhatsNewIfPresent, loginAsOwner } from "./fixtures/auth";

const CBZ = readFileSync(join(process.cwd(), "e2e/fixtures/comic-pages.cbz"));

test("a comic turns from the cover to the next page", async ({ page }) => {
  await loginAsOwner(page);
  await page.route("**/api/works/work-cbz", async (route) => {
    if (route.request().method() !== "GET") {
      await route.fallback();
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        work: {
          id: "work-cbz",
          title: "Creepshow",
          author: "King, Stephen",
          kind: "comic",
          year: 2013,
          description: "A comic for the reading room.",
          review_state: "none",
        },
        files: [{ id: "c1", filename: "Creepshow.cbz", kind: "comic", size: CBZ.length, reading_room: true }],
        file_count: 1,
        can_open: true,
        can_download: true,
        can_read: true,
        listen: { can_listen: false },
        komga: null,
        audiobook: null,
        favorite: false,
        related: [],
        progress: { fraction: 0, position: "" },
        ebook_convert: false,
        formats: [],
        series_ribbon: [],
        whispers: [],
      }),
    });
  });
  await page.route("**/api/works/work-cbz/download**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/vnd.comicbook+zip",
      headers: { "content-disposition": 'inline; filename="Creepshow.cbz"' },
      body: CBZ,
    });
  });
  await page.route("**/api/works/work-cbz/progress", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: "{}" });
  });

  await page.setViewportSize({ width: 1100, height: 800 });
  await page.goto("/works/work-cbz?read=1");
  await dismissWhatsNewIfPresent(page);
  const reader = page.getByTestId("reader");
  await expect(reader).toBeVisible({ timeout: 30_000 });
  await expect(reader.getByText("Scroll to read")).toHaveCount(0);
  await expect(reader.getByRole("button", { name: "Next page" })).toBeVisible();

  const sectionIndex = () => page.evaluate(() => {
    const view = document.querySelector("foliate-view") as HTMLElement & {
      renderer?: { index?: number; getAttribute(name: string): string | null };
    };
    return {
      index: view?.renderer?.index ?? -1,
      flow: view?.renderer?.getAttribute("flow") || "",
    };
  });
  await expect.poll(async () => (await sectionIndex()).index, { timeout: 20_000 }).toBe(0);
  expect((await sectionIndex()).flow).not.toBe("scrolled");

  await reader.getByRole("button", { name: "Next page" }).click();
  await expect.poll(async () => (await sectionIndex()).index, { timeout: 10_000 }).toBe(1);

  await page.keyboard.press("ArrowRight");
  await expect.poll(async () => (await sectionIndex()).index, { timeout: 10_000 }).toBe(2);

  await page.keyboard.press("ArrowLeft");
  await expect.poll(async () => (await sectionIndex()).index, { timeout: 10_000 }).toBe(1);
});
