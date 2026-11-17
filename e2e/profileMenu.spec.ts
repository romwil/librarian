import { expect, test } from "@playwright/test";
import { dismissWhatsNewIfPresent, loginAsOwner } from "./fixtures/auth";

/**
 * Library card panel must stay fully usable — not clipped under the sticky
 * topbar or past the viewport bottom. Desktop + phone (390).
 *
 * The panel itself must fit in the viewport (placement + max-height). Owner
 * links may live in a scrollable panel; scroll each into view before checking
 * its box — layout boxes of overflowed children can sit past the viewport.
 */

async function openLibraryCard(page: import("@playwright/test").Page) {
  await page.getByRole("button", { name: /^Library card\b/ }).click();
  await expect(page.getByRole("dialog", { name: "Library card" })).toBeVisible();
}

async function assertPanelFitsViewport(page: import("@playwright/test").Page) {
  const viewport = page.viewportSize()!;
  const panel = page.getByRole("dialog", { name: "Library card" });
  const box = await panel.boundingBox();
  expect(box, "panel box").toBeTruthy();
  expect(box!.y, "panel top").toBeGreaterThanOrEqual(0);
  expect(box!.y + box!.height, "panel bottom").toBeLessThanOrEqual(viewport.height + 1);
  expect(box!.x, "panel left").toBeGreaterThanOrEqual(0);
  expect(box!.x + box!.width, "panel right").toBeLessThanOrEqual(viewport.width + 1);
}

async function assertOwnerLinksReachable(page: import("@playwright/test").Page) {
  const viewport = page.viewportSize()!;
  const panel = page.getByRole("dialog", { name: "Library card" });
  const names = ["Settings", "People", "Downloads", "Logout"] as const;
  for (const name of names) {
    const link =
      name === "Logout" ? panel.getByRole("button", { name }) : panel.getByRole("link", { name });
    await link.scrollIntoViewIfNeeded();
    await expect(link).toBeVisible();
    const box = await link.boundingBox();
    expect(box, `${name} should have a box`).toBeTruthy();
    expect(box!.y, `${name} top`).toBeGreaterThanOrEqual(0);
    expect(box!.y + box!.height, `${name} bottom`).toBeLessThanOrEqual(viewport.height + 1);
  }
  const sorting = panel.getByTestId("profile-sorting-link");
  await sorting.scrollIntoViewIfNeeded();
  await expect(sorting).toBeVisible();
  const sortingBox = await sorting.boundingBox();
  expect(sortingBox).toBeTruthy();
  expect(sortingBox!.y + sortingBox!.height).toBeLessThanOrEqual(viewport.height + 1);
}

test.describe("Library card profile menu placement", () => {
  test("desktop owner menu keeps Settings through Logout in viewport", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 720 });
    await loginAsOwner(page);
    await page.goto("/");
    await dismissWhatsNewIfPresent(page);
    await openLibraryCard(page);
    await assertPanelFitsViewport(page);
    await assertOwnerLinksReachable(page);
  });

  test("390 owner menu keeps Settings through Logout in viewport", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await loginAsOwner(page);
    await page.goto("/");
    await dismissWhatsNewIfPresent(page);
    await openLibraryCard(page);
    await assertPanelFitsViewport(page);
    await assertOwnerLinksReachable(page);
  });
});
