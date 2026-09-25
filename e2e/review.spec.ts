import { expect, test } from "@playwright/test";
import { dismissWhatsNewIfPresent, loginAsOwner } from "./fixtures/auth";

test.describe("Review / Holds desk", () => {
  test.beforeEach(async ({ page }) => {
    await loginAsOwner(page);
  });

  test("empty Review shows Holds desk empty copy", async ({ page }) => {
    await page.goto("/review");
    await dismissWhatsNewIfPresent(page);
    await expect(page.getByText("Holds desk").first()).toBeVisible();
    await expect(page.getByRole("heading", { name: "Review" })).toBeVisible();
    // Lexicon: Holds desk empty copy; semantic text, not testid.
    await expect(page.getByText(/Holds desk is empty|lamp is quiet/i)).toBeVisible({
      timeout: 30_000,
    });
  });
});
