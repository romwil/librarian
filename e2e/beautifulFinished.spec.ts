import { expect, test, type Page } from "@playwright/test";
import { dismissWhatsNewIfPresent, loginAsOwner } from "./fixtures/auth";

/** Work detail for Beautiful Finished ceremony (D2 reader lane). */
const WORK_DETAIL = {
  work: {
    id: "work-kindred",
    title: "Kindred",
    author: "Octavia Butler",
    kind: "book",
    year: 1979,
    description: "A quiet volume under the lamp.",
    review_state: "none",
  },
  files: [{ id: "f1", filename: "Kindred.epub", kind: "book", size: 1200 }],
  file_count: 1,
  can_open: true,
  can_download: true,
  can_read: true,
  listen: { can_listen: false },
  komga: null,
  audiobook: null,
  favorite: false,
  related: [],
  progress: { fraction: 0.4, position: "" },
  ebook_convert: false,
  formats: [],
  series_ribbon: [],
  whispers: [],
};

async function mockWorkPage(page: Page) {
  await page.route("**/api/works/work-kindred", async (route) => {
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
  await page.route("**/api/works/work-kindred/progress", async (route) => {
    if (route.request().method() !== "POST") {
      await route.fallback();
      return;
    }
    const posted = route.request().postDataJSON() as { finished?: boolean; whisper?: string };
    const whisper = String(posted.whisper || "").trim();
    const body: Record<string, unknown> = {
      progress: { fraction: 1, position: "", work_id: "work-kindred" },
    };
    if (whisper) {
      body.whisper = {
        id: "w1",
        work_id: "work-kindred",
        body: whisper,
        author_name: "e2e-owner",
      };
      body.whispers = [body.whisper];
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(body),
    });
  });
}

test.describe("Beautiful Finished", () => {
  test.beforeEach(async ({ page }) => {
    await loginAsOwner(page);
  });

  test("Finished opens ceremony with optional household whisper", async ({ page }) => {
    await mockWorkPage(page);
    await page.goto("/works/work-kindred");
    await expect(page.getByRole("heading", { name: "Kindred" })).toBeVisible({ timeout: 30_000 });
    await dismissWhatsNewIfPresent(page);

    const finished = page.getByRole("button", { name: "Finished" });
    await expect(finished).toBeVisible();
    await finished.click();

    const ceremony = page.getByRole("region", { name: "Finished ceremony" });
    await expect(ceremony).toBeVisible();
    await expect(ceremony.getByText(/lamp remembers/i)).toBeVisible();
    await expect(ceremony.getByText("Leave a quiet note for the house?")).toBeVisible();
    await expect(page.getByText(/bagging/i)).toHaveCount(0);

    await page.getByLabel("Quiet note for the house").fill("Left it warm on the table.");
    await ceremony.getByRole("button", { name: "Whisper to the house" }).click();

    await expect(ceremony).toHaveCount(0);
    await expect(page.getByText(/lamp remembers/i)).toBeVisible();
    await expect(page.getByTestId("family-whispers").getByText("Left it warm on the table.")).toBeVisible();
  });

  test("Just finished completes without a whisper", async ({ page }) => {
    await mockWorkPage(page);
    await page.goto("/works/work-kindred");
    await expect(page.getByRole("heading", { name: "Kindred" })).toBeVisible({ timeout: 30_000 });
    await dismissWhatsNewIfPresent(page);

    await page.getByRole("button", { name: "Finished" }).click();
    const ceremony = page.getByRole("region", { name: "Finished ceremony" });
    await expect(ceremony).toBeVisible();
    await ceremony.getByRole("button", { name: "Just finished" }).click();
    await expect(ceremony).toHaveCount(0);
    await expect(page.getByText(/lamp remembers/i)).toBeVisible();
  });

  test("reduced-motion keeps ceremony readable and static", async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await mockWorkPage(page);
    await page.goto("/works/work-kindred");
    await expect(page.getByRole("heading", { name: "Kindred" })).toBeVisible({ timeout: 30_000 });
    await dismissWhatsNewIfPresent(page);

    await page.getByRole("button", { name: "Finished" }).click();
    const ceremony = page.getByRole("region", { name: "Finished ceremony" });
    await expect(ceremony).toBeVisible();
    await expect(ceremony.getByText(/lamp remembers/i)).toBeVisible();

    const breathToken = await page.evaluate(() =>
      getComputedStyle(document.documentElement).getPropertyValue("--motion-ritual").trim(),
    );
    expect(breathToken).toBe("1ms");

    const running = await ceremony.evaluate((node) =>
      [node, ...node.querySelectorAll("*")].filter(
        (el) => getComputedStyle(el as Element).animationName !== "none",
      ).length,
    );
    expect(running).toBe(0);
  });
});
