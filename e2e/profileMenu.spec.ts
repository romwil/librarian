import { expect, test } from "@playwright/test";
import { dismissWhatsNewIfPresent, loginAsOwner } from "./fixtures/auth";

/**
 * Library card panel must stay fully usable — not clipped under the sticky
 * topbar or past the viewport bottom. Desktop + phone (390).
 */

async function openLibraryCard(page: import("@playwright/test").Page) {
  await page.getByRole("button", { name: /^Library card\b/ }).click();
  await expect(page.getByRole("dialog", { name: "Library card" })).toBeVisible();
}

async function assertOwnerMenuUsable(page: import("@playwright/test").Page) {
  const panel = page.getByRole("dialog", { name: "Library card" });
  const panelBox = await panel.boundingBox();
  expect(panelBox).toBeTruthy();
  const view = page.viewportSize()!;
  expect(panelBox!.y).toBeGreaterThanOrEqual(0);
  expect(panelBox!.y + panelBox!.height).toBeLessThanOrEqual(view.height + 1);
  expect(panelBox!.x).toBeGreaterThanOrEqual(0);
  expect(panelBox!.x + panelBox!.width).toBeLessThanOrEqual(view.width + 1);

  for (const name of ["Settings", "People", "Downloads", "Logout"]) {
    const target =
      name === "Logout" ? panel.getByRole("button", { name }) : panel.getByRole("link", { name });
    await target.scrollIntoViewIfNeeded();
    await expect(target).toBeVisible();
    await expect(target).toBeInViewport();
  }
  const sorting = panel.getByTestId("profile-sorting-link");
  await sorting.scrollIntoViewIfNeeded();
  await expect(sorting).toBeVisible();
  await expect(sorting).toBeInViewport();
}

test.describe("Library card profile menu placement", () => {
  test("desktop owner menu keeps Settings through Logout in viewport", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 720 });
    await loginAsOwner(page);
    await page.goto("/");
    await dismissWhatsNewIfPresent(page);
    await openLibraryCard(page);
    await assertOwnerMenuUsable(page);
  });

  test("390 owner menu keeps Settings through Logout in viewport", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await loginAsOwner(page);
    await page.goto("/");
    await dismissWhatsNewIfPresent(page);
    await openLibraryCard(page);
    await assertOwnerMenuUsable(page);
  });
});
