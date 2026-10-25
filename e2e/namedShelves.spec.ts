import { expect, test } from "@playwright/test";
import { dismissWhatsNewIfPresent, loginAsOwner } from "./fixtures/auth";

test.describe("Named household shelves", () => {
  test.beforeEach(async ({ page }) => {
    await loginAsOwner(page);
    await dismissWhatsNewIfPresent(page);
  });

  test("Stacks opens household shelves", async ({ page }) => {
    await page.goto("/browse");
    await expect(page.getByRole("heading", { name: "The stacks" })).toBeVisible({ timeout: 30_000 });
    const shelf = page.getByRole("combobox", { name: "Shelf" });
    await expect(shelf).toBeVisible();
    await expect(shelf.getByRole("option", { name: "Favorites" })).toHaveCount(1);
    await expect(page.getByRole("heading", { name: "Name a shelf" })).toBeVisible();
    await expect(page.getByRole("textbox", { name: "Shelf name" })).toBeVisible();
    await expect(page.getByRole("checkbox", { name: "Share with the house" })).toBeChecked();
    await expect(page.getByRole("button", { name: "Name this shelf" })).toBeVisible();

    await page.goto("/");
    await expect(page.getByRole("search")).toBeVisible({ timeout: 30_000 });
    await expect(page.getByRole("heading", { name: "Name a shelf" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "More shelves" })).toHaveCount(0);
  });
});
