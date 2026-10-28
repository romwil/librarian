import { expect, test, type Page } from "@playwright/test";
import { dismissWhatsNewIfPresent, loginAsOwner } from "./fixtures/auth";

type Slip = Record<string, unknown>;

function slip(id: string, title: string, reason: string, extra: Slip = {}): Slip {
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
    ...extra,
  };
}

async function mockDesk(page: Page, initial: Slip[]) {
  const state = { works: [...initial] };
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
        works: state.works,
        llm_configured: false,
        extra_files_count: 0,
        needs_review_count: state.works.length,
      }),
    });
  });
  return state;
}

test.describe("Holds desk group actions", () => {
  test.beforeEach(async ({ page }) => {
    await loginAsOwner(page);
  });

  test("Delete group confirms, Escape returns focus, then deletes the pile", async ({ page }) => {
    const state = await mockDesk(page, [
      slip("low-1", "Odd One", "low_confidence"),
      slip("low-2", "Odd Two", "low_confidence"),
      slip("col-1", "Twin", "collision"),
    ]);
    const bodies: Record<string, unknown>[] = [];
    await page.route("**/api/review/bulk-by-reason", async (route) => {
      const body = route.request().postDataJSON();
      bodies.push(body);
      state.works = state.works.filter((w) => !(body.work_ids as string[]).includes(String(w.id)));
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          action: "delete",
          reason: body.reason,
          examined: 2,
          changed: 2,
          skipped: 0,
          failed: 0,
          reasons: {},
          failures: [],
        }),
      });
    });

    await page.goto("/review");
    await dismissWhatsNewIfPresent(page);
    const lowActions = page.getByRole("group", { name: "Low confidence group actions" });
    await expect(lowActions).toBeVisible({ timeout: 30_000 });
    await expect(lowActions.getByRole("button", { name: "Purge duplicate group" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: /re-want/i })).toHaveCount(0);

    const trigger = lowActions.getByRole("button", { name: "Delete group (2)" });
    await trigger.click();
    const dialog = page.getByRole("dialog", { name: /Delete 2 hold slips/ });
    await expect(dialog).toBeVisible();
    await expect(dialog).toContainText(/completed-download folder is not deleted/);
    await expect(dialog.getByRole("button", { name: "Cancel" })).toBeFocused();
    await page.keyboard.press("Escape");
    await expect(dialog).toHaveCount(0);
    await expect(trigger).toBeFocused();
    expect(bodies).toHaveLength(0);

    await trigger.click();
    await page.getByRole("dialog").getByRole("button", { name: "Delete 2 slips" }).click();
    await expect(page.getByTestId("review-group-note")).toContainText("Deleted 2 of 2.");
    await expect(page.getByTestId("review-group-note")).toContainText("Download folders stay on disk");
    expect(bodies[0]).toMatchObject({ reason: "low_confidence", action: "delete", work_ids: ["low-1", "low-2"] });
    await expect(page.getByRole("heading", { name: /Low confidence/ })).toHaveCount(0);
    await expect(page.getByRole("heading", { name: /Collision/ })).toBeVisible();
  });

  test("Purge duplicate group previews evidence, then reports a partial failure", async ({ page }) => {
    await mockDesk(page, [
      slip("col-1", "Twin", "collision"),
      slip("col-2", "Unreadable", "collision"),
      slip("col-3", "Broken", "collision"),
    ]);
    const bodies: Record<string, unknown>[] = [];
    await page.route("**/api/review/bulk-by-reason", async (route) => {
      const body = route.request().postDataJSON();
      bodies.push(body);
      const payload = body.dry_run
        ? {
            action: "purge_duplicates",
            dry_run: true,
            examined: 3,
            changed: 0,
            purgeable: 2,
            unassessable: 1,
            evidence: { exact_fingerprint: 2, unassessable: 1 },
            reasons: {},
          }
        : {
            action: "purge_duplicates",
            examined: 3,
            changed: 1,
            skipped: 2,
            failed: 1,
            reasons: { unassessable: 1, failed: 1 },
            failures: [{ id: "col-3", title: "Broken", error: "database is locked" }],
          };
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(payload) });
    });

    await page.goto("/review");
    await dismissWhatsNewIfPresent(page);
    const actions = page.getByRole("group", { name: "Collision group actions" });
    await actions.getByRole("button", { name: "Purge duplicate group" }).click();
    const dialog = page.getByRole("dialog", { name: "Purge 2 exact duplicates?" });
    await expect(dialog).toContainText("2 exact fingerprint");
    await expect(dialog).toContainText("1 unassessable");
    await expect(page.getByTestId("holds-group-evidence")).toContainText("2 exact fingerprint · 1 unassessable");
    expect(bodies).toHaveLength(1);
    expect(bodies[0]).toMatchObject({ dry_run: true });

    await dialog.getByRole("button", { name: "Purge 2" }).click();
    const pileResult = page.getByTestId("holds-group-result");
    await expect(pileResult).toContainText("Purged 1 of 3. Skipped 2: 1 unassessable, 1 failed.");
    await expect(pileResult).toContainText("Broken: database is locked");
    await expect(page.getByTestId("review-group-note")).toHaveCount(0);
    expect(bodies[1]).toMatchObject({ dry_run: false, action: "purge_duplicates" });
  });

  test("group header actions stay reachable on a phone", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 740 });
    await mockDesk(page, [slip("col-1", "Twin", "collision"), slip("col-2", "Twin Two", "collision")]);
    await page.goto("/review");
    await dismissWhatsNewIfPresent(page);
    const actions = page.getByRole("group", { name: "Collision group actions" });
    const purge = actions.getByRole("button", { name: "Purge duplicate group" });
    const del = actions.getByRole("button", { name: "Delete group (2)" });
    await expect(purge).toBeVisible({ timeout: 30_000 });
    await expect(del).toBeVisible();
    for (const button of [purge, del]) {
      const box = await button.boundingBox();
      expect(box).not.toBeNull();
      expect(box!.x).toBeGreaterThanOrEqual(0);
      expect(box!.x + box!.width).toBeLessThanOrEqual(375 + 1);
    }
    const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
    expect(scrollWidth).toBeLessThanOrEqual(375 + 1);
  });

  test("model triage counts update live while the server job runs", async ({ page }) => {
    let polls = 0;
    const slips = [
      slip("t-1", "alpha.Audio.book", "low_confidence", {
        actions: { can_suggest_llm: true, needs_llm_suggest: true, llm_configured: true },
      }),
      slip("t-2", "bravo.Audio.book", "low_confidence", {
        actions: { can_suggest_llm: true, needs_llm_suggest: true, llm_configured: true },
      }),
    ];
    await page.route("**/api/settings/quiet-hours", (route) =>
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({}) }),
    );
    await page.route("**/api/review/bad-release-migration/status", (route) =>
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "idle" }) }),
    );
    let started = false;
    await page.route("**/api/review/suggest-batch", async (route) => {
      started = true;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ status: "running", done: 0, total: 2, kicked_off: true }),
      });
    });
    await page.route("**/api/review/suggest-batch/status", async (route) => {
      if (!started) {
        await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "idle" }) });
        return;
      }
      polls += 1;
      const done = Math.min(2, polls);
      const body =
        done < 2
          ? { status: "running", done, total: 2, suggested: done, trusted: 1, ambiguous: 0, failed: 0 }
          : { status: "completed", done: 2, total: 2, suggested: 2, trusted: 1, ambiguous: 1, failed: 0 };
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
    });
    await page.route("**/api/review", async (route) => {
      const settled = Math.min(2, polls);
      const works = slips.map((row, index) => {
        if (index >= settled) return row;
        const outcome = index === 0 ? "trusted" : "ambiguous";
        return {
          ...row,
          effective_reason: outcome === "trusted" ? "ready_to_file" : "low_confidence",
          llm_triage: {
            outcome,
            label: outcome === "trusted" ? "Ready to file" : "Needs a decision",
            explanation: outcome === "trusted" ? "" : "Missing author.",
            suggestion: { title: index === 0 ? "Alpha" : "Bravo" },
          },
        };
      });
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ works, needs_review_count: works.length }),
      });
    });

    await page.goto("/review");
    await dismissWhatsNewIfPresent(page);
    await page.getByRole("button", { name: "Check low-confidence slips (2)" }).click();
    await expect(page.getByTestId("review-triage-counts")).toContainText("1 ready to file", { timeout: 15_000 });
    await expect(page.getByTestId("review-triage-counts")).toContainText(
      "1 ready to file · 1 need a decision · 0 model unavailable",
      { timeout: 15_000 },
    );
    await expect(page.getByRole("heading", { name: /Ready to file/ })).toBeVisible();
    await expect(page.getByRole("button", { name: "Apply trusted matches (1)" })).toBeVisible();
    await expect(page.getByTestId("review-model-triage")).toContainText("2 sent: 1 ready to file, 1 need a decision");
  });
});
