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
    await expect(page.getByRole("heading", { name: "Sorting returns" })).toBeVisible();
    await expect(page.getByText(/Hold slips are returns waiting to be sorted/i)).toBeVisible();
    // Lexicon: Holds desk empty copy; semantic text, not testid.
    await expect(page.getByText(/Holds desk is empty|lamp is quiet/i)).toBeVisible({
      timeout: 30_000,
    });
  });

  test("populated Holds desk groups slips by reason with one recommended motion", async ({
    page,
  }) => {
    await page.route("**/api/review", async (route) => {
      if (route.request().method() !== "GET") {
        await route.continue();
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          works: [
            {
              id: "extra-1",
              title: "Fiction Dump",
              kind: "book",
              author: "",
              review_reason: "extra_files",
              folder_diagnosis: { collection_dump: true, distinct_title_count: 5 },
              actions: {
                can_repair: false,
                can_retry: false,
                recommended_motion: "clear_extra_files",
                find_query: "Fiction Dump",
              },
            },
            {
              id: "unpack-1",
              title: "Guardians Archive",
              kind: "audiobook",
              author: "VA",
              review_reason: "unpack_stuck",
              folder_diagnosis: { problem: "unpack_stuck", archive_count: 2, par2_count: 1 },
              actions: {
                can_repair: true,
                can_retry: true,
                recommended_motion: "repair",
                find_query: "Guardians Archive",
              },
            },
            {
              id: "collision-1",
              title: "Already Shelved",
              kind: "book",
              author: "Author",
              review_reason: "collision",
              folder_diagnosis: {},
              actions: {
                can_repair: false,
                can_retry: false,
                recommended_motion: "skip",
                find_query: "Already Shelved",
              },
            },
          ],
          llm_configured: false,
          extra_files_count: 1,
          needs_review_count: 3,
        }),
      });
    });
    await page.route("**/api/settings/quiet-hours", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          quiet_hours_enabled: false,
          quiet_hours_start: "22:00",
          quiet_hours_end: "07:00",
          active_now: false,
        }),
      });
    });

    await page.goto("/review");
    await dismissWhatsNewIfPresent(page);
    await expect(page.getByRole("heading", { name: "Sorting returns" })).toBeVisible();
    await expect(page.getByTestId("holds-desk-groups")).toBeVisible({ timeout: 30_000 });

    const groups = page.getByTestId("holds-group");
    await expect(groups).toHaveCount(3);
    await expect(page.getByRole("heading", { name: /Extra files/i })).toBeVisible();
    await expect(page.getByRole("heading", { name: /Unpack stuck/i })).toBeVisible();
    await expect(page.getByRole("heading", { name: /Collision/i })).toBeVisible();

    await expect(page.getByTestId("holds-group-motion").first()).toContainText(/Recommended:/i);
    await expect(page.getByTestId("hold-slip")).toHaveCount(3);
    await expect(page.getByTestId("hold-slip-recommended").first()).toContainText(/Recommended:/i);

    // One recommended primary CTA on the unpack pile — Repair filled, not a flat ticket queue.
    const unpackGroup = page.locator('[data-testid="holds-group"][data-reason="unpack_stuck"]');
    await expect(unpackGroup.getByRole("button", { name: "Repair" })).toBeVisible();
    await expect(unpackGroup.getByTestId("hold-slip-recommended")).toContainText("Repair");
  });
});
