import { expect, test } from "@playwright/test";
import { loginAsOwner } from "./fixtures/auth";

test.describe("Search lanes", () => {
  test("local covers paint before any beyond fetch; CTA starts beyond", async ({ page }) => {
    let beyondHits = 0;
    await loginAsOwner(page);
    await page.route("**/api/search/beyond**", async (route) => {
      beyondHits += 1;
      await new Promise((resolve) => setTimeout(resolve, 400));
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          beyond: [{ title: "Dune NZB", guid: "g-dune", kind: "book" }],
          public_domain: [],
          beyond_error: null,
        }),
      });
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
          local: [
            {
              id: "w-dune",
              title: "Dune on the shelf",
              author: "Frank Herbert",
              kind: "book",
              has_cover: false,
            },
          ],
          beyond: [],
          public_domain: [],
        }),
      });
    });
    const started = Date.now();
    await page.goto("/search?q=dune");
    await expect(page.getByRole("button", { name: /^Dune on the shelf/ }).first()).toBeVisible({
      timeout: 1000,
    });
    expect(Date.now() - started).toBeLessThan(1000);
    expect(beyondHits).toBe(0);
    await expect(page.getByRole("button", { name: "Search beyond the shelves" })).toBeVisible();
    await expect(page.getByTestId("search-beyond")).toHaveCount(0);

    await page.getByRole("button", { name: "Search beyond the shelves" }).click();
    await expect(page.getByTestId("search-beyond")).toBeVisible();
    await expect(page.getByTestId("search-beyond")).toHaveAttribute("aria-busy", "true");
    await expect(page.getByTestId("skeleton-rail")).toBeVisible();
    await expect(page.getByTestId("search-status")).toContainText(/looking beyond/i);
    await expect(page.getByRole("button", { name: /^Dune NZB/ }).first()).toBeVisible({
      timeout: 5000,
    });
    await expect(page.getByTestId("search-beyond")).toHaveAttribute("aria-busy", "false");
    expect(beyondHits).toBe(1);
  });

  test("reader submit stays on the shelf and offers Ask the house", async ({ page }) => {
    await loginAsOwner(page);
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
        }),
      });
    });
    await page.goto("/search?q=dune");
    await expect(page.getByRole("button", { name: /^Dune on the shelf/ }).first()).toBeVisible();
    await expect(page.getByRole("button", { name: "Ask the house" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Search beyond the shelves" })).toHaveCount(0);
    await expect(page.getByRole("heading", { name: "Beyond the shelves" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Discover" })).toHaveCount(0);
  });
});
