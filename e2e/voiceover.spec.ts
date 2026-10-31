import { expect, test, type Page } from "@playwright/test";
import { dismissWhatsNewIfPresent, loginAsOwner } from "./fixtures/auth";

const BOOK = {
  work: {
    id: "vo-book",
    title: "The Quiet Room",
    author: "A. Lamp",
    kind: "book",
    year: 2020,
    review_state: "none",
  },
  files: [{ id: "f1", filename: "Quiet.epub", kind: "book", size: 800, reading_room: true }],
  file_count: 1,
  can_open: true,
  can_download: true,
  can_read: true,
  listen: { can_listen: false },
  favorite: false,
  related: [],
  whispers: [],
  progress: { fraction: 0.1, position: "" },
};

const AUDIOBOOK = {
  work: {
    id: "vo-listen",
    title: "Long Listen",
    author: "N. Arrator",
    kind: "audiobook",
    review_state: "",
  },
  can_download: true,
  can_read: false,
  files: [
    { id: "p1", filename: "Part 1.m4b" },
    { id: "p2", filename: "Part 2.m4b" },
  ],
  file_count: 2,
  favorite: false,
  listen: { can_listen: true },
  related: [],
  whispers: [],
};

async function mockWork(page: Page, id: string, body: unknown) {
  await page.route(`**/api/works/${id}`, async (route) => {
    if (route.request().method() !== "GET") {
      await route.fallback();
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(body),
    });
  });
}

test.describe("VoiceOver script — named landmarks", () => {
  test("login names the foyer and the Enter control", async ({ page }) => {
    await page.goto("/login");
    await expect(page).toHaveTitle(/Sign in/);
    await expect(page.getByRole("heading", { name: "The Reading Room" })).toBeVisible();
    await expect(page.getByRole("textbox", { name: "Name" })).toBeVisible();
    await expect(page.getByLabel("Password", { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Enter" })).toBeVisible();
  });

  test("join names Name, Password, and Enter", async ({ page }) => {
    await page.route("**/api/invites/validate**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          invite: { role: "reader", expires_at: "2099-12-31T00:00:00Z" },
        }),
      });
    });
    await page.goto("/join?token=vo-join-token");
    await expect(page).toHaveTitle(/Join/);
    await expect(page.getByRole("heading", { name: "The Reading Room" })).toBeVisible();
    await expect(page.getByRole("textbox", { name: "Name" })).toBeVisible();
    await expect(page.getByLabel("Password", { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Enter" })).toBeVisible();
  });

  test("Read names the volume and the reading room dialog", async ({ page }) => {
    await loginAsOwner(page);
    await mockWork(page, "vo-book", BOOK);
    await page.goto("/works/vo-book");
    await dismissWhatsNewIfPresent(page);
    await expect(page.getByRole("heading", { name: "The Quiet Room" })).toBeVisible();
    await page.getByRole("button", { name: "Read", exact: true }).click();
    await expect(page.getByRole("dialog", { name: "The Quiet Room" })).toBeVisible();
  });

  test("Listen names the volume and the listening room dialog", async ({ page }) => {
    await loginAsOwner(page);
    await mockWork(page, "vo-listen", AUDIOBOOK);
    await page.route("**/api/works/vo-listen/chapters**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ chapters: [] }),
      });
    });
    await page.goto("/works/vo-listen");
    await dismissWhatsNewIfPresent(page);
    await expect(page.getByRole("heading", { name: "Long Listen" })).toBeVisible();
    await page.getByRole("button", { name: "Listen", exact: true }).first().click();
    await expect(page.getByRole("dialog", { name: "Long Listen" })).toBeVisible();
  });

  test("Sorting names the desk heading", async ({ page }) => {
    await loginAsOwner(page);
    await page.goto("/review");
    await expect(page).toHaveTitle(/Sorting/);
    await expect(page.getByRole("heading", { name: "Sorting", exact: true })).toBeVisible();
    await expect(page.getByRole("navigation", { name: "Library" })).toBeVisible();
  });
});
