import { expect, test, type Page } from "@playwright/test";
import { dismissWhatsNewIfPresent, loginAsOwner } from "./fixtures/auth";

const LISTEN_BOOK = {
  id: "book-listen",
  kind: "book",
  title: "Dune",
  author: "Frank Herbert",
  audiobook: {
    applicable: true,
    shelved: { id: "audio-dune", title: "Dune", author: "Frank Herbert", kind: "audiobook" },
    find: { kind: "audiobook", title: "Dune", author: "Frank Herbert" },
  },
};

const WANTED_BOOK = {
  id: "book-want",
  kind: "book",
  title: "Circe",
  author: "Madeline Miller",
  audiobook: {
    applicable: true,
    shelved: null,
    find: { kind: "audiobook", title: "Circe", author: "Madeline Miller", isbn: "9780316556347" },
  },
};

async function mockBrowse(page: Page) {
  await page.route("**/api/browse**", async (route) => {
    const url = new URL(route.request().url());
    if (!url.pathname.endsWith("/browse")) {
      await route.fallback();
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        items: [LISTEN_BOOK, WANTED_BOOK],
        total: 2,
        offset: 0,
        limit: 48,
        sort: "author",
        filters: { kind: "", author: "", letter: "", series: "", genre: "", shelf: "" },
      }),
    });
  });
}

async function viewAsReader(page: Page) {
  await page.route("**/api/auth/me", async (route) => {
    const response = await route.fetch();
    const data = await response.json();
    if (data?.user) data.user.role = "reader";
    await route.fulfill({
      status: response.status(),
      contentType: "application/json",
      body: JSON.stringify(data),
    });
  });
}

test.describe("Library availability", () => {
  test("Browse cards name the book and leave a missing audiobook off the list", async ({ page }) => {
    await loginAsOwner(page);
    await mockBrowse(page);
    await page.goto("/browse");
    await dismissWhatsNewIfPresent(page);
    const circe = page.getByRole("button", { name: "Circe", exact: true });
    const dune = page.getByRole("button", { name: "Dune", exact: true });
    await expect(circe).toBeVisible();
    await expect(circe).toContainText("Madeline Miller");
    await expect(dune).toBeVisible();
    await expect(dune).toContainText("Frank Herbert");
    await expect(page.getByText("The audiobook is wanted")).toHaveCount(0);
    await expect(page.getByRole("link", { name: "Listen" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Add to Wanted" })).toHaveCount(0);
    await expect(page.getByText("On the shelf")).toHaveCount(0);
  });

  test("Wanted desk add and dismiss stay with the owner", async ({ page }) => {
    await loginAsOwner(page);
    await page.goto("/wanted");
    await dismissWhatsNewIfPresent(page);
    await expect(page.getByRole("heading", { name: "Wanted", exact: true })).toBeVisible();
    const title = `Lantern ${Date.now()}`;
    await page.getByRole("textbox", { name: "Title" }).fill(title);
    await page.getByRole("textbox", { name: "Author" }).fill("A. Lamp");
    await page.getByTestId("wanted-add-submit").click();
    const row = page.getByTestId("wanted-row").filter({ hasText: title });
    await expect(row).toBeVisible();
    await expect(row.getByRole("button", { name: "Find beyond" })).toBeVisible();
    await row.getByTestId("wanted-dismiss").click();
    await expect(row).toHaveCount(0);
  });

  test("a reader can open Wanted and cannot add or dismiss", async ({ page }) => {
    await viewAsReader(page);
    await loginAsOwner(page);
    await page.goto("/wanted");
    await dismissWhatsNewIfPresent(page);
    await expect(page.getByRole("heading", { name: "Wanted", exact: true })).toBeVisible();
    await expect(page.getByTestId("wanted-add")).toHaveCount(0);
    await expect(page.getByTestId("wanted-dismiss")).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Add to Wanted" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Dismiss", exact: true })).toHaveCount(0);
  });
});
