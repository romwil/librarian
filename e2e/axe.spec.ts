import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { dismissWhatsNewIfPresent, loginAsOwner } from "./fixtures/auth";

const WORK = {
  work: {
    id: "seed-1",
    title: "Seeded Volume",
    author: "A. Reader",
    kind: "book",
    year: 1965,
    review_state: "",
  },
  can_download: false,
  can_read: false,
  files: [],
  file_count: 0,
  favorite: false,
  listen: { can_listen: false },
};

async function setTheme(page: Page, name: "Lights Up" | "Lights Down") {
  const testId = name === "Lights Up" ? "profile-theme-lights_up" : "profile-theme-lights_down";
  await page.getByTestId("profile-menu-trigger").click();
  await page.getByTestId(testId).click();
  await page.locator(".room").evaluate((el) => {
    el.setAttribute("data-ambient", "off");
  });
  await page.keyboard.press("Escape");
}

/** Let page-settle / soft-enter fades finish: axe samples colors mid-fade otherwise. */
async function settleMotion(page: Page) {
  await page.evaluate(() =>
    Promise.all(
      document
        .getAnimations()
        .filter((animation) => Number.isFinite(animation.effect?.getComputedTiming().endTime))
        .map((animation) => animation.finished.catch(() => undefined)),
    ),
  );
}

async function assertAxe(page: Page) {
  await settleMotion(page);
  const results = await new AxeBuilder({ page }).analyze();
  const summary = results.violations
    .map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join("; ")}`)
    .join("\n");
  expect(results.violations, summary).toEqual([]);
}

function slip(id: string, title: string, reason: string) {
  return {
    id,
    title,
    kind: "book",
    author: "Ann Author",
    review_reason: reason,
    effective_reason: reason,
    folder_path: `/data/complete/${id}`,
    folder_diagnosis: {},
    actions: { recommended_motion: reason === "collision" ? "skip" : "apply", find_query: title },
  };
}

async function mockSortingDesk(page: Page) {
  await page.route("**/api/settings/quiet-hours", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ quiet_hours_enabled: false, active_now: false }),
    }),
  );
  await page.route("**/api/review/suggest-batch/status", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "idle" }) }),
  );
  await page.route("**/api/review/bad-release-migration/status", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ status: "completed", total: 0, done: 0, returned: 0, left_on_desk: 0, failed: 0 }),
    }),
  );
  await page.route("**/api/review", async (route) => {
    if (route.request().method() !== "GET") {
      await route.continue();
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        works: [slip("low-1", "Odd One", "low_confidence"), slip("low-2", "Odd Two", "low_confidence")],
        llm_configured: false,
        extra_files_count: 0,
        needs_review_count: 2,
      }),
    });
  });
  await page.route("**/api/review/bulk-by-reason", async (route) => {
    const body = route.request().postDataJSON() as Record<string, unknown>;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        action: body.action,
        reason: body.reason,
        dry_run: true,
        would_change: 2,
        requires_typed_count: false,
        examined: 2,
        changed: 0,
      }),
    });
  });
}

test.describe("axe-core", () => {
  test("login foyer", async ({ page }) => {
    await page.goto("/login");
    await expect(page.getByRole("heading", { name: "The Reading Room" })).toBeVisible();
    await assertAxe(page);
  });

  test("join paste", async ({ page }) => {
    await page.goto("/join");
    await expect(page.getByLabel("Invite link")).toBeVisible();
    await assertAxe(page);
  });

  test("join with token", async ({ page }) => {
    await page.route("**/api/invites/validate**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          invite: { role: "reader", expires_at: "2099-12-31T00:00:00Z" },
        }),
      });
    });
    await page.goto("/join?token=axe-join-token");
    await expect(page.getByRole("textbox", { name: "Name" })).toBeVisible();
    await expect(page.getByLabel("Password", { exact: true })).toBeVisible();
    await assertAxe(page);
  });

  test("reset missing token", async ({ page }) => {
    await page.goto("/reset");
    await expect(page.getByRole("heading", { name: "New key" })).toBeVisible();
    await expect(page.getByRole("alert")).toBeVisible();
    await assertAxe(page);
  });

  test("join 320px", async ({ page }) => {
    await page.setViewportSize({ width: 320, height: 720 });
    await page.goto("/join");
    await expect(page.getByLabel("Invite link")).toBeVisible();
    await assertAxe(page);
  });

  for (const theme of ["Lights Up", "Lights Down"] as const) {
    test.describe(theme, () => {
      test.beforeEach(async ({ page }) => {
        await loginAsOwner(page);
        await setTheme(page, theme);
      });

      test("Hall", async ({ page }) => {
        await page.goto("/");
        await dismissWhatsNewIfPresent(page);
        await expect(page.getByRole("heading", { name: "Hall" })).toBeVisible();
        await assertAxe(page);
      });

      test("Search", async ({ page }) => {
        await page.goto("/search");
        await expect(page.getByRole("search")).toBeVisible();
        await assertAxe(page);
      });

      test("Work", async ({ page }) => {
        await page.route("**/api/works/seed-1", async (route) => {
          await route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify(WORK),
          });
        });
        await page.goto("/works/seed-1");
        await expect(page.getByRole("heading", { name: "Seeded Volume" })).toBeVisible();
        await assertAxe(page);
      });

      test("Sorting", async ({ page }) => {
        await page.goto("/review");
        await expect(page.getByRole("heading", { name: "Sorting", exact: true })).toBeVisible();
        await assertAxe(page);
      });

      test("Settings", async ({ page }) => {
        await page.goto("/settings");
        await expect(page.getByRole("heading", { name: /Settings/i })).toBeVisible();
        await assertAxe(page);
      });

      test("Library card", async ({ page }) => {
        await page.goto("/card");
        await expect(page.getByRole("heading", { name: "Your library" })).toBeVisible();
        await assertAxe(page);
      });
    });
  }

  test("What’s New overlay", async ({ page }) => {
    await loginAsOwner(page, { dismissWhatsNew: false });
    await expect(page.getByRole("dialog", { name: /What’s new/i })).toBeVisible({ timeout: 10_000 });
    await assertAxe(page);
  });

  test.describe("overlays and 320px", () => {
    test.beforeEach(async ({ page }) => {
      await loginAsOwner(page);
      await setTheme(page, "Lights Up");
    });

    test("invite dialog", async ({ page }) => {
      await page.goto("/people");
      await expect(page.getByRole("heading", { name: "People" })).toBeVisible();
      await page.getByRole("button", { name: "Invite a reader" }).click();
      await expect(page.getByRole("dialog", { name: "This invite is shown once" })).toBeVisible();
      await expect(page.getByText(/\/join\?token=/)).toBeVisible();
      await assertAxe(page);
    });

    test("Queue to SAB confirm", async ({ page }) => {
      await page.route("**/api/queue", async (route) => {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            jobs: [{ id: "job-asked", status: "asked", title: "Asked Volume" }],
          }),
        });
      });
      await page.goto("/queue");
      await expect(page.getByRole("heading", { name: "Downloads" })).toBeVisible();
      await page.getByRole("button", { name: "Queue to SAB" }).click();
      await expect(page.getByRole("dialog", { name: "Send to the downloader?" })).toBeVisible();
      await assertAxe(page);
    });

    test("purge typed confirm", async ({ page }) => {
      await page.route("**/api/maintain/purge-shells/preview**", async (route) => {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            would_purge: 3,
            candidates: 3,
            on_shelves: 0,
            with_progress: 0,
            sample: ["Ghost One", "Ghost Two"],
            kept_reasons: { wishlist_stub: 1, has_payload: 0, needs_review: 0 },
          }),
        });
      });
      await page.goto("/maintain");
      await expect(page.getByRole("heading", { name: "Maintain" })).toBeVisible();
      await page.getByRole("button", { name: /Purge shells/ }).click();
      await expect(page.getByRole("dialog", { name: "Purge unshelved shells" })).toBeVisible();
      await assertAxe(page);
    });

    test("Sorting group preview", async ({ page }) => {
      await mockSortingDesk(page);
      await page.goto("/review");
      await expect(page.getByRole("heading", { name: "Sorting", exact: true })).toBeVisible();
      await page.getByRole("button", { name: /Delete group/ }).click();
      await expect(page.getByRole("dialog")).toBeVisible();
      await assertAxe(page);
    });

    test("Ask the house disclosure", async ({ page }) => {
      await page.evaluate(() => localStorage.removeItem("librarian.searchBeyondDisclosure"));
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
      await page.route("**/api/search/beyond**", async (route) => {
        await route.fulfill({ status: 403, contentType: "application/json", body: "{}" });
      });
      await page.route(/\/api\/search(\?|$)/, async (route) => {
        if (route.request().url().includes("/api/search/beyond")) {
          await route.fallback();
          return;
        }
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            local: [{ id: "w-dune", title: "Dune on the shelf", author: "Frank Herbert", kind: "book" }],
            beyond: [],
            public_domain: [],
            can_beyond: false,
            beyond_disclosure: { indexers: ["NZBFinder"], model: "the house model", publicDomain: [] },
          }),
        });
      });
      await page.goto("/search?q=dune");
      await dismissWhatsNewIfPresent(page);
      await expect(page.getByRole("button", { name: "Ask the house" })).toBeVisible();
      await page.getByRole("button", { name: "Ask the house" }).click();
      await expect(page.getByRole("dialog", { name: "Ask the house?" })).toBeVisible();
      await assertAxe(page);
    });

    test("sign-out-everywhere", async ({ page }) => {
      await page.goto("/card");
      await expect(page.getByRole("heading", { name: "Your library" })).toBeVisible();
      await page.getByRole("button", { name: "Sign out everywhere" }).click();
      await expect(page.getByRole("dialog", { name: "Sign out everywhere?" })).toBeVisible();
      await assertAxe(page);
    });

    test("password form on Library card", async ({ page }) => {
      await page.goto("/card");
      await expect(page.getByRole("textbox", { name: "Current password" })).toBeVisible();
      await expect(page.getByRole("textbox", { name: "New password" })).toBeVisible();
      await assertAxe(page);
    });

    test("Hall 320px", async ({ page }) => {
      await page.setViewportSize({ width: 320, height: 720 });
      await page.goto("/");
      await dismissWhatsNewIfPresent(page);
      await expect(page.getByRole("heading", { name: "Hall" })).toBeVisible();
      await assertAxe(page);
    });

    test("Sorting 320px", async ({ page }) => {
      await page.setViewportSize({ width: 320, height: 720 });
      await page.goto("/review");
      await expect(page.getByRole("heading", { name: "Sorting", exact: true })).toBeVisible();
      await assertAxe(page);
    });
  });
});
