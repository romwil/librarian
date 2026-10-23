import { expect, test } from "@playwright/test";
import { dismissWhatsNewIfPresent, loginAsOwner } from "./fixtures/auth";

test.describe("Settings nav", () => {
  test.beforeEach(async ({ page }) => {
    await loginAsOwner(page);
  });

  test("Settings page exposes section nav and Appearance panel", async ({ page }) => {
    await page.goto("/settings");
    await dismissWhatsNewIfPresent(page);
    await expect(page.getByRole("heading", { name: "Settings" })).toBeVisible({ timeout: 30_000 });
    await expect(page.getByRole("navigation", { name: "Settings sections" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Appearance" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Shelving" })).toBeVisible();
    await page.getByRole("button", { name: "Appearance" }).click();
    await expect(page.getByText("Your appearance")).toBeVisible();
    await expect(page.getByRole("slider", { name: "Text size" })).toBeVisible();
  });

  test("Library card menu opens from the top bar", async ({ page }) => {
    await page.goto("/");
    await dismissWhatsNewIfPresent(page);
    await page.getByRole("button", { name: "Library card" }).click();
    await expect(page.getByRole("menu")).toBeVisible();
    await expect(page.getByRole("menuitem", { name: "Inbox" })).toBeVisible();
    await expect(page.getByRole("radiogroup", { name: "Theme" })).toBeVisible();
  });

  test("Library card text size slider keeps the menu open", async ({ page }) => {
    await page.goto("/");
    await dismissWhatsNewIfPresent(page);
    await page.getByRole("button", { name: "Library card" }).click();
    const menu = page.getByRole("menu");
    await expect(menu).toBeVisible();

    const slider = page.getByRole("slider", { name: /Text size/ });
    await expect(slider).toBeVisible();
    await page.getByRole("menu").getByText("Text size").click();
    await expect(menu).toBeVisible();
    await page.getByRole("menu").getByText("Default").click();
    await expect(menu).toBeVisible();

    const box = await slider.boundingBox();
    expect(box).toBeTruthy();
    await page.mouse.click(box.x + box.width * 0.7, box.y + box.height / 2);
    await expect(menu).toBeVisible();

    const before = Number(await slider.inputValue());
    await slider.focus();
    await page.keyboard.press("ArrowRight");
    await expect(menu).toBeVisible();
    const after = Number(await slider.inputValue());
    expect(after).toBeGreaterThan(before);
    await expect(slider).toHaveAttribute("aria-valuenow", String(after));
    const baseFont = await page.evaluate(() =>
      getComputedStyle(document.documentElement).getPropertyValue("--base-font-size").trim(),
    );
    expect(baseFont).not.toEqual("");

    await page.keyboard.press("Escape");
    await expect(menu).toHaveCount(0);

    await page.getByRole("button", { name: "Library card" }).click();
    await expect(menu).toBeVisible();
    await page.getByRole("heading", { name: "Hall" }).click();
    await expect(menu).toHaveCount(0);
  });

  test("Settings Mail section is reachable from nav", async ({ page }) => {
    await page.goto("/settings");
    await dismissWhatsNewIfPresent(page);
    await expect(page.getByRole("heading", { name: "Settings" })).toBeVisible({ timeout: 30_000 });
    await page.getByRole("button", { name: "Mail" }).click();
    await expect(page.getByRole("heading", { name: "Outbound email" })).toBeVisible();
    await expect(page.getByLabel("Provider")).toBeVisible();
    await expect(page.getByRole("button", { name: "Send test email" })).toBeVisible();
  });
});
