import { expect, test } from "@playwright/test";
import { dismissWhatsNewIfPresent, loginAsOwner } from "./fixtures/auth";

test.describe("Sweep intent", () => {
  test("Wanted rows name Sweep vs Owner want and offer bulk dismiss", async ({ page }) => {
    await loginAsOwner(page);
    await page.route("**/api/wanted**", async (route) => {
      const url = new URL(route.request().url());
      if (route.request().method() !== "GET" || !url.pathname.endsWith("/wanted")) {
        await route.fallback();
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          items: [
            {
              id: "w-sweep",
              title: "Circe",
              author: "Madeline Miller",
              kind: "audiobook",
              status: "wanted",
              source: "sweep",
              restorable: false,
            },
            {
              id: "w-owner",
              title: "Kindred",
              author: "Octavia Butler",
              kind: "audiobook",
              status: "wanted",
              source: "manual",
              restorable: false,
            },
          ],
          total: 2,
          page: 1,
          page_size: 50,
          kinds: ["audiobook"],
          sweep: { enabled: true, open: 1, cap: 200, restorable: 0 },
        }),
      });
    });
    await page.goto("/wanted");
    await dismissWhatsNewIfPresent(page);
    await expect(page.getByRole("heading", { name: "Wanted", exact: true })).toBeVisible();
    const sweepRow = page.getByTestId("wanted-row").filter({ hasText: "Circe" });
    const ownerRow = page.getByTestId("wanted-row").filter({ hasText: "Kindred" });
    await expect(sweepRow.getByText("Sweep")).toBeVisible();
    await expect(ownerRow.getByText("Owner want")).toBeVisible();
    await expect(page.getByRole("button", { name: "Dismiss sweep wants" })).toBeEnabled();
    await expect(page.getByRole("button", { name: "Turn automatic audiobook wants off" })).toBeVisible();
  });
});
