import { expect, test } from "@playwright/test";
import { dismissWhatsNewIfPresent, loginAsOwner } from "./fixtures/auth";

const WORK_ID = "edition-work";

const EDITION_WORK = {
  work: {
    id: WORK_ID,
    title: "The Left Hand of Darkness",
    author: "Ursula K. Le Guin",
    kind: "book",
    review_state: "",
  },
  can_download: true,
  can_read: true,
  files: [{ id: "epub", filename: "left-hand.epub", kind: "book", reading_room: true, on_disk: true }],
  file_count: 1,
  favorite: false,
  listen: { can_listen: false },
  editions: [
    { id: "ed-hard", kind: "book", isbn13: "9780441478125", asin: null, format: "Hardcover" },
    { id: "ed-audio", kind: "audiobook", isbn13: null, asin: "B00LEFT", format: "Audiobook" },
  ],
  related: [],
  whispers: [],
};

const STACKS_BOOK = {
  id: "stacks-1",
  title: "The Left Hand of Darkness",
  author: "Ursula K. Le Guin",
  kind: "book",
  has_cover: false,
  favorite: false,
};

function pathIs(url: URL, pathname: string) {
  return url.pathname === pathname;
}

async function fulfillJson(route: { fulfill: (opts: object) => Promise<void> }, body: unknown) {
  await route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

test.describe("Canonical works", () => {
  test.beforeEach(async ({ page }) => {
    await loginAsOwner(page);
  });

  test("work page lists editions with format and identifiers", async ({ page }) => {
    await page.route(
      (url) => pathIs(url, `/api/works/${WORK_ID}`),
      async (route) => {
        if (route.request().method() !== "GET") {
          await route.fallback();
          return;
        }
        await fulfillJson(route, EDITION_WORK);
      },
    );
    await page.route(
      (url) => pathIs(url, `/api/works/${WORK_ID}/progress`),
      async (route) => {
        await fulfillJson(route, { progress: null });
      },
    );

    await page.goto(`/works/${WORK_ID}`);
    await dismissWhatsNewIfPresent(page);
    await expect(page.getByRole("heading", { name: "The Left Hand of Darkness", exact: true })).toBeVisible();

    const editions = page.getByRole("region", { name: "Editions and formats" });
    await expect(editions).toBeVisible();
    const rows = editions.getByRole("listitem");
    await expect(rows).toHaveCount(2);
    await expect(rows.filter({ hasText: "9780441478125" })).toContainText("Hardcover");
    await expect(rows.filter({ hasText: "B00LEFT" })).toContainText("Audiobook");
    await expect(rows.filter({ hasText: "B00LEFT" })).toContainText("ASIN");
  });

  test("Stacks cover shows title and author without On the shelf or Read", async ({ page }) => {
    await page.route(
      (url) => pathIs(url, "/api/browse"),
      async (route) => {
        await fulfillJson(route, {
          items: [STACKS_BOOK],
          total: 1,
          offset: 0,
          limit: 48,
          sort: "author",
          sort_dir: "asc",
          filters: {},
        });
      },
    );

    await page.goto("/browse");
    await dismissWhatsNewIfPresent(page);
    await expect(page.getByRole("heading", { name: "The stacks", exact: true })).toBeVisible();

    const cover = page.getByRole("button", { name: "The Left Hand of Darkness", exact: true });
    await expect(cover).toBeVisible();
    // Cloth byline plus the footer under the cover. One copy means the footer is gone.
    await expect(page.getByText("The Left Hand of Darkness", { exact: true })).toHaveCount(2);
    await expect(page.getByText("Ursula K. Le Guin", { exact: true })).toHaveCount(2);
    await expect(page.getByText("On the shelf", { exact: true })).toHaveCount(0);
    await expect(page.getByRole("link", { name: "Read", exact: true })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Read", exact: true })).toHaveCount(0);
  });

  test("Discover stays closed until expanded, then requests ebook trending", async ({ page }) => {
    const discoverUrls: string[] = [];
    await page.route(
      (url) => pathIs(url, "/api/discover"),
      async (route) => {
        const url = route.request().url();
        discoverUrls.push(url);
        const offset = Number(new URL(url).searchParams.get("offset") || 0);
        const count = offset === 0 ? 12 : 3;
        const items = Array.from({ length: count }, (_, index) => ({
          guid: `g-${offset + index}`,
          title: `Ebook ${offset + index}`,
          kind: "book",
          category: "7020",
        }));
        await fulfillJson(route, { items, categories: [], limit: 12, offset });
      },
    );

    await page.goto("/search");
    await dismissWhatsNewIfPresent(page);
    const toggle = page.getByRole("button", { name: "Discover", exact: true });
    await expect(page.getByRole("search").getByLabel("Search")).toBeVisible();
    await expect(page.getByRole("link", { name: "New & noted" })).toHaveCount(1);
    await expect(toggle).toHaveAttribute("aria-expanded", "false");
    await expect(page.getByRole("button", { name: "Previous", exact: true })).toHaveCount(0);
    expect(discoverUrls).toEqual([]);

    await toggle.click();
    await expect(toggle).toHaveAttribute("aria-expanded", "true");
    await expect(page.getByRole("button", { name: "Ebook 0", exact: true })).toBeVisible();
    expect(discoverUrls).toHaveLength(1);
    const first = new URL(discoverUrls[0]);
    expect(first.pathname).toBe("/api/discover");
    expect(first.searchParams.get("cat")).toBe("7020");
    expect(first.searchParams.get("limit")).toBe("12");
    expect(first.searchParams.get("kind")).toBeNull();
    expect(first.searchParams.get("offset")).toBeNull();
    await expect(page.getByRole("button", { name: "Previous", exact: true })).toBeDisabled();

    await page.getByRole("button", { name: "Book", exact: true }).click();
    await expect(page.getByRole("button", { name: "Book", exact: true })).toHaveAttribute("aria-pressed", "true");
    expect(discoverUrls).toHaveLength(1);

    await page.getByRole("button", { name: "Next", exact: true }).click();
    await expect(page.getByRole("button", { name: "Ebook 12", exact: true })).toBeVisible();
    expect(discoverUrls).toHaveLength(2);
    const second = new URL(discoverUrls[1]);
    expect(second.searchParams.get("cat")).toBe("7020");
    expect(second.searchParams.get("limit")).toBe("12");
    expect(second.searchParams.get("offset")).toBe("12");
    expect(second.searchParams.get("kind")).toBeNull();
  });

  test("New & noted switches one cached list without another fetch", async ({ page }) => {
    let notedGets = 0;
    await page.route(
      (url) => pathIs(url, "/api/noted"),
      async (route) => {
        if (route.request().method() !== "GET") {
          await route.fallback();
          return;
        }
        notedGets += 1;
        await fulfillJson(route, {
          can_add: true,
          lists: [
            { id: "open-library-daily", label: "Open Library daily" },
            { id: "nyt-hardcover-fiction", label: "Hardcover Fiction" },
          ],
          lanes: [
            {
              id: "open-library-daily",
              label: "Open Library daily",
              items: [{ title: "Daily Title", author: "Daily Author", kind: "book" }],
            },
            {
              id: "nyt-hardcover-fiction",
              label: "Hardcover Fiction",
              items: [{ title: "Fiction Title", author: "Fiction Author", kind: "book" }],
            },
          ],
        });
      },
    );

    await page.goto("/noted");
    await dismissWhatsNewIfPresent(page);
    await expect(page.getByRole("heading", { name: "New & noted", exact: true })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Open Library daily", exact: true })).toBeVisible();
    await expect(page.getByText("Daily Title", { exact: true })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Hardcover Fiction", exact: true })).toHaveCount(0);
    const fetchesAfterLoad = notedGets;
    expect(fetchesAfterLoad).toBeGreaterThan(0);

    await page.evaluate(() => {
      (window as Window & { __notedStamp?: string }).__notedStamp = "kept";
    });
    await page.getByRole("button", { name: "Hardcover Fiction", exact: true }).click();
    await expect(page.getByRole("button", { name: "Hardcover Fiction", exact: true })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await expect(page.getByRole("button", { name: "Open Library daily", exact: true })).toHaveAttribute(
      "aria-pressed",
      "false",
    );
    await expect(page.getByRole("heading", { name: "Hardcover Fiction", exact: true })).toBeVisible();
    await expect(page.getByText("Fiction Title", { exact: true })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Open Library daily", exact: true })).toHaveCount(0);
    await expect(page.getByText("Daily Title", { exact: true })).toHaveCount(0);
    await expect(page).toHaveURL(/\/noted$/);
    expect(notedGets).toBe(fetchesAfterLoad);
    expect(await page.evaluate(() => (window as Window & { __notedStamp?: string }).__notedStamp)).toBe("kept");
  });

  test("owner date range can add missing noted titles", async ({ page }) => {
    const history = {
      items: [
        {
          title: "Missing Novel",
          author: "Ada Author",
          isbn13: "9780000000001",
          weeks: ["2026-04-05"],
          shelved: false,
        },
        {
          title: "Already Here",
          author: "Bea Author",
          isbn13: "9780000000002",
          weeks: ["2026-04-12"],
          shelved: true,
        },
      ],
    };
    const historyUrls: string[] = [];
    const posted: unknown[] = [];
    await page.route(
      (url) => pathIs(url, "/api/noted/history"),
      async (route) => {
        historyUrls.push(route.request().url());
        await fulfillJson(route, history);
      },
    );
    await page.route(
      (url) => pathIs(url, "/api/noted/history/add-missing"),
      async (route) => {
        posted.push(route.request().postDataJSON());
        await fulfillJson(route, { added: 1 });
      },
    );

    await page.goto("/noted/history");
    await dismissWhatsNewIfPresent(page);
    await expect(page.getByRole("heading", { name: "New & noted history", exact: true })).toBeVisible();
    await page.getByLabel("NYT category").selectOption("hardcover-fiction");
    await page.getByLabel("Start date").fill("2026-04-01");
    await page.getByLabel("End date").fill("2026-04-30");
    await page.getByRole("button", { name: "Load range", exact: true }).click();

    await expect(page.getByText("Missing Novel", { exact: true })).toBeVisible();
    await expect(page.getByText("Already Here", { exact: true })).toBeVisible();
    await expect(page.getByText("2026-04-05")).toHaveCount(0);
    await expect(page.getByText("2026-04-12")).toHaveCount(0);
    await expect(page.getByText("Missing", { exact: true })).toBeVisible();
    await expect(page.getByText("Matched", { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Add to Wanted" })).toBeVisible();
    expect(historyUrls).toHaveLength(1);
    const loaded = new URL(historyUrls[0]);
    expect(loaded.searchParams.get("list_name")).toBe("hardcover-fiction");
    expect(loaded.searchParams.get("start")).toBe("2026-04-01");
    expect(loaded.searchParams.get("end")).toBe("2026-04-30");

    await page.getByRole("button", { name: "Add missing", exact: true }).click();
    await expect(page.getByText("Added 1 missing title to Wanted.", { exact: true })).toBeVisible();
    expect(posted).toHaveLength(1);
    const body = posted[0] as { items: { title: string }[] };
    expect(body.items.map((item) => item.title)).toEqual(["Missing Novel", "Already Here"]);
    expect(historyUrls).toHaveLength(2);
  });

  test("possible duplicates pile is visible on mocked Sorting", async ({ page }) => {
    await page.route(
      (url) => pathIs(url, "/api/review"),
      async (route) => {
        if (route.request().method() !== "GET") {
          await route.fallback();
          return;
        }
        await fulfillJson(route, {
          works: [
            {
              id: "dup-1",
              title: "Twin Copy",
              kind: "book",
              author: "Ann Author",
              review_reason: "possible_duplicate",
              folder_diagnosis: {},
              actions: { recommended_motion: "skip", find_query: "Twin Copy" },
            },
            {
              id: "dup-2",
              title: "Twin Copy Again",
              kind: "book",
              author: "Ann Author",
              review_reason: "possible_duplicate",
              folder_diagnosis: {},
              actions: { recommended_motion: "skip", find_query: "Twin Copy Again" },
            },
          ],
          llm_configured: false,
          extra_files_count: 0,
          needs_review_count: 2,
        });
      },
    );
    await page.route(
      (url) => pathIs(url, "/api/settings/quiet-hours"),
      async (route) => {
        await fulfillJson(route, { quiet_hours_enabled: false, active_now: false });
      },
    );

    await page.goto("/review");
    await dismissWhatsNewIfPresent(page);
    const pile = page.getByRole("region", { name: /Possible duplicate/ });
    await expect(pile).toBeVisible({ timeout: 30_000 });
    await expect(pile.getByRole("heading", { name: /Possible duplicate/ })).toBeVisible();
    await expect(pile.getByText("Twin Copy", { exact: true })).toBeVisible();
    await expect(pile.getByText("Twin Copy Again", { exact: true })).toBeVisible();
    await expect(
      pile.getByText("Title and author match a shelved work — Skip keeps the shelf copy."),
    ).toBeVisible();
    await expect(pile.getByRole("button", { name: "Purge duplicate group", exact: true })).toBeVisible();
    await expect(pile.getByRole("button", { name: "Skip", exact: true })).toHaveCount(2);
  });
});
