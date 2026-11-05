import { readFileSync } from "node:fs";
import { join } from "node:path";
import { expect, test } from "@playwright/test";
import { dismissWhatsNewIfPresent, loginAsOwner } from "./fixtures/auth";

const PDF = readFileSync(join(process.cwd(), "e2e/fixtures/two-pages.pdf"));

test("a PDF opens past the splash and turns a page", async ({ page }) => {
  await loginAsOwner(page);
  await page.route("**/api/works/work-pdf", async (route) => {
    if (route.request().method() !== "GET") {
      await route.fallback();
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        work: {
          id: "work-pdf",
          title: "Monster And Ghost, Vol 03",
          author: "TOKYOPOP",
          kind: "comic",
          year: 2026,
          description: "A PDF comic for the reading room.",
          review_state: "none",
        },
        files: [{ id: "p1", filename: "Monster.And.Ghost.Vol.03.pdf", kind: "comic", size: PDF.length, reading_room: true }],
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
  await page.route("**/api/works/work-pdf/download**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/pdf",
      headers: {
        "content-disposition": 'inline; filename="Monster.And.Ghost.Vol.03.pdf"',
        "accept-ranges": "bytes",
        "content-length": String(PDF.length),
      },
      body: PDF,
    });
  });
  await page.route("**/api/works/work-pdf/progress", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: "{}" });
  });

  await page.setViewportSize({ width: 1100, height: 800 });
  await page.goto("/works/work-pdf?read=1");
  await dismissWhatsNewIfPresent(page);
  const reader = page.getByRole("dialog", { name: "Monster And Ghost, Vol 03" });
  await expect(reader).toBeVisible({ timeout: 30_000 });
  await expect(reader.getByText("Opening the volume…")).toHaveCount(0, { timeout: 20_000 });
  await expect(reader.getByRole("img", { name: "Page 1 of 2" })).toBeVisible({ timeout: 20_000 });
  await expect(reader.getByRole("button", { name: "Next page" })).toBeVisible();

  await reader.getByRole("button", { name: "Next page" }).click();
  await expect(reader.getByRole("img", { name: "Page 2 of 2" })).toBeVisible({ timeout: 10_000 });

  await reader.getByRole("button", { name: "Previous page" }).click();
  await expect(reader.getByRole("img", { name: "Page 1 of 2" })).toBeVisible({ timeout: 10_000 });
});
