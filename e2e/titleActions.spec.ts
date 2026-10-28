import { expect, test, type Page } from "@playwright/test";
import { loginAsOwner } from "./fixtures/auth";

/** One unbreakable token long enough to blow a list row that forgets to clip. */
const LONG_TITLE = `Night Reading ${"Unbroken".repeat(28)}`;
const WORK_ID = "long-shelf";

const LONG_WORK = {
  id: WORK_ID,
  title: LONG_TITLE,
  author: "Ada Shelf",
  year: 1888,
  kind: "book",
  series_name: "",
  genre: "Essays",
  favorite: false,
  has_cover: false,
};

const WORK_DETAIL = {
  work: LONG_WORK,
  files: [{ id: "f1", filename: "night-reading.epub", kind: "book", size: 1200, on_disk: true }],
  file_count: 1,
  can_open: true,
  can_download: true,
  can_read: true,
  listen: { can_listen: false },
  komga: null,
  audiobook: null,
  favorite: false,
  related: [],
  progress: null,
  ebook_convert: false,
  formats: [],
};

const VIEWPORTS = [
  { name: "desktop", width: 1280, height: 800 },
  { name: "phone", width: 390, height: 844 },
] as const;

const LAMPS = ["Lights Up", "Lights Down"] as const;

function isBrowseList(url: URL) {
  return url.pathname === "/api/browse";
}

async function mockStacks(page: Page) {
  await page.route(isBrowseList, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        items: [LONG_WORK],
        total: 1,
        offset: 0,
        limit: 48,
        sort: "author",
        sort_dir: "asc",
        filters: {},
      }),
    });
  });
  await page.route(
    (url) => url.pathname === `/api/works/${WORK_ID}`,
    async (route) => {
      if (route.request().method() !== "GET") {
        await route.fallback();
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(WORK_DETAIL),
      });
    },
  );
  await page.route(
    (url) => url.pathname === `/api/works/${WORK_ID}/progress`,
    async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ progress: { fraction: 0, position: "", work_id: WORK_ID } }),
      });
    },
  );
}

async function chooseLamp(page: Page, lamp: (typeof LAMPS)[number]) {
  await page.getByRole("button", { name: /^Library card\b/ }).click();
  const theme = page.getByRole("radiogroup", { name: "Theme" });
  await theme.getByRole("radio", { name: lamp, exact: true }).click();
  await expect
    .poll(() => page.evaluate(() => document.documentElement.getAttribute("data-theme")))
    .toBe(lamp === "Lights Up" ? "lights-up" : "lights-down");
  await page.keyboard.press("Escape");
}

async function expectShelfCurrent(
  page: Page,
  which: "stacks" | "favorites",
  viewport: (typeof VIEWPORTS)[number]["name"],
) {
  const nav = page.getByRole("navigation", { name: viewport === "desktop" ? "Library" : "Mobile" });
  const stacks = nav.getByRole("link", { name: "Stacks", exact: true });
  const favorites = nav.getByRole("link", { name: "Favorites", exact: true });
  if (which === "stacks") {
    await expect(stacks).toHaveAttribute("aria-current", "page");
    await expect(favorites).not.toHaveAttribute("aria-current", "page");
  } else {
    await expect(favorites).toHaveAttribute("aria-current", "page");
    await expect(stacks).not.toHaveAttribute("aria-current", "page");
  }
}

async function expectChromeForViewport(page: Page, viewport: (typeof VIEWPORTS)[number]["name"]) {
  const reader = page.getByRole("navigation", { name: "Library" });
  const mobile = page.getByRole("navigation", { name: "Mobile" });
  if (viewport === "desktop") {
    await expect(reader.getByRole("link", { name: "Hall", exact: true })).toBeVisible();
    await expect(reader.getByRole("link", { name: "Stacks", exact: true })).toBeVisible();
    await expect(reader.getByRole("link", { name: "Search", exact: true })).toBeVisible();
    await expect(reader.getByRole("link", { name: "Favorites", exact: true })).toBeVisible();
    await expect(mobile).toBeHidden();
  } else {
    await expect(reader).toBeHidden();
    await expect(mobile.getByRole("link", { name: "Hall", exact: true })).toBeVisible();
    await expect(mobile.getByRole("link", { name: "Stacks", exact: true })).toBeVisible();
    await expect(mobile.getByRole("link", { name: "Search", exact: true })).toBeVisible();
    await expect(mobile.getByRole("link", { name: "Favorites", exact: true })).toBeVisible();
  }
}

/** Favorite and Download live in the grip. The first menu row can take focus. */
async function openGripAndFocusFirstRow(page: Page, title: string, { strayDownload = false } = {}) {
  const grip = page.getByRole("button", { name: `Actions for ${title}`, exact: true });
  await expect(page.getByRole("button", { name: "Favorite", exact: true })).toHaveCount(0);
  if (!strayDownload) {
    await expect(page.getByRole("link", { name: "Download", exact: true })).toHaveCount(0);
  }
  await grip.focus();
  await expect(grip).toBeFocused();
  await page.keyboard.press("Enter");
  const menu = page.getByRole("menu", { name: `Actions for ${title}`, exact: true });
  await expect(menu).toBeVisible();
  const first = menu.getByRole("button").first();
  await expect(first).toHaveAccessibleName("Favorite");
  await first.focus();
  await expect(first).toBeFocused();
  await expect(menu.getByRole("link", { name: "Download", exact: true })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(menu).toBeHidden();
}

async function expectListRowFits(page: Page) {
  const titleLink = page.getByRole("link", { name: LONG_TITLE, exact: true });
  await expect(titleLink).toBeVisible();
  const fit = await titleLink.evaluate((node) => {
    const row = node.parentElement?.parentElement;
    const linkBox = node.getBoundingClientRect();
    const rowBox = row?.getBoundingClientRect();
    const doc = document.documentElement;
    return {
      pageOverflow: doc.scrollWidth - doc.clientWidth,
      rowWidth: rowBox?.width ?? 0,
      rowRight: rowBox?.right ?? 0,
      linkRight: linkBox.right,
      viewport: window.innerWidth,
    };
  });
  expect(fit.rowWidth).toBeLessThanOrEqual(fit.viewport + 1);
  expect(fit.rowRight).toBeLessThanOrEqual(fit.viewport + 1);
  expect(fit.linkRight).toBeLessThanOrEqual(fit.viewport + 1);
  expect(fit.pageOverflow).toBeLessThanOrEqual(1);
}

for (const viewport of VIEWPORTS) {
  for (const lamp of LAMPS) {
    test(`${lamp} at ${viewport.name}: stacks bar, grip focus, long title`, async ({ page }) => {
      await page.setViewportSize({ width: viewport.width, height: viewport.height });
      await loginAsOwner(page);
      await mockStacks(page);
      await chooseLamp(page, lamp);
      await expectChromeForViewport(page, viewport.name);

      await page.goto("/browse?shelf=favorites");
      await expect(page.getByRole("heading", { name: "Favorites", exact: true })).toBeVisible();
      await expectShelfCurrent(page, "favorites", viewport.name);

      await page.goto("/browse");
      await expect(page.getByRole("heading", { name: "The stacks", exact: true })).toBeVisible();
      await expectShelfCurrent(page, "stacks", viewport.name);
      await expectChromeForViewport(page, viewport.name);

      const filters = page.getByRole("button", { name: "Filters", exact: true });
      if (viewport.name === "phone") {
        await expect(filters).toBeVisible();
        await expect(page.getByLabel("Kind")).toBeHidden();
        await filters.click();
      } else {
        await expect(filters).toBeHidden();
      }
      await expect(page.getByLabel("Kind")).toBeVisible();
      const sort = page.getByRole("combobox", { name: "Sort", exact: true });
      await expect(sort).toBeVisible();
      await expect(page.getByRole("group", { name: "View" }).getByRole("button", { name: "Covers" })).toBeVisible();
      // Date added opens newest-first. The direction control is named for the
      // direction a click would switch to, so descending offers ascending.
      await expect(sort).toHaveValue("updated");
      await expect(page.getByRole("button", { name: "Sort Ascending", exact: true })).toBeVisible();
      await sort.selectOption({ label: "Year" });
      await expect(sort).toHaveValue("year");
      await expect(page.getByRole("button", { name: "Sort Ascending", exact: true })).toBeVisible();

      await page.getByRole("button", { name: "Export CSV", exact: true }).click();
      await expect(page.getByRole("link", { name: "Visible columns", exact: true })).toBeVisible();
      await expect(page.getByRole("link", { name: "All columns", exact: true })).toBeVisible();
      await page.keyboard.press("Escape");

      await openGripAndFocusFirstRow(page, LONG_TITLE);
      const coverMenu = page.getByRole("menu", { name: `Actions for ${LONG_TITLE}`, exact: true });
      await page.getByRole("button", { name: `Actions for ${LONG_TITLE}`, exact: true }).click();
      await expect(coverMenu.getByRole("link", { name: "Read", exact: true })).toBeVisible();
      await expect(coverMenu.getByRole("link", { name: "Open full page", exact: true })).toBeVisible();
      await page.keyboard.press("Escape");

      await page.getByRole("group", { name: "View" }).getByRole("button", { name: "List", exact: true }).click();
      await expectListRowFits(page);

      await page.goto(`/works/${WORK_ID}`);
      await expect(page.getByRole("heading", { name: LONG_TITLE, exact: true })).toBeVisible();
      await expect(page.getByRole("button", { name: "Read", exact: true })).toBeVisible();
      await expect(page.getByRole("button", { name: "Finished", exact: true })).toBeVisible();
      await openGripAndFocusFirstRow(page, LONG_TITLE, { strayDownload: true });
      await expect(page.getByRole("button", { name: "Read", exact: true })).toBeVisible();
    });
  }
}

test("stacks loading holds, then an empty shelf", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await loginAsOwner(page);
  let release = () => {};
  const gate = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route(isBrowseList, async (route) => {
    await gate;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        items: [],
        total: 0,
        offset: 0,
        limit: 48,
        sort: "author",
        sort_dir: "asc",
        filters: {},
      }),
    });
  });
  await page.goto("/browse");
  await expect(page.getByRole("heading", { name: "The stacks", exact: true })).toBeVisible();
  await expect(page.getByText("Warming the lamp on these stacks…")).toBeVisible();
  release();
  await expect(page.getByText("Nothing matches these shelves yet.")).toBeVisible();
  await expect(page.getByText("Warming the lamp on these stacks…")).toBeHidden();
  await expect(page.getByLabel("Kind")).toBeVisible();
});
