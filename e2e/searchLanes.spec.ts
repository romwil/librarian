import { expect, test } from "@playwright/test";
import { loginAsOwner } from "./fixtures/auth";

test.describe("Search lanes", () => {
  test("delayed beyond still shows local covers under a second", async ({ page }) => {
    await loginAsOwner(page);
    await page.route("**/api/search/beyond**", async (route) => {
      await new Promise((resolve) => setTimeout(resolve, 2500));
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ beyond: [], public_domain: [], beyond_error: null }),
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
    await expect(page.getByRole("heading", { name: "Beyond the shelves" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Discover" })).toHaveCount(0);
  });
});
