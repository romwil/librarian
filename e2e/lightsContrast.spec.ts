import { expect, test, type Page } from "@playwright/test";
import { dismissWhatsNewIfPresent, loginAsOwner, setTheme } from "./fixtures/auth";
import {
  backgroundAlpha,
  expectReadable,
  mockPeekHall,
  PEEK_WORK,
} from "./fixtures/contrast";

const LAMPS = ["Lights Up", "Lights Down"] as const;

async function openRevengePeek(page: Page) {
  await mockPeekHall(page);
  await page.goto("/");
  await dismissWhatsNewIfPresent(page);
  await page.getByRole("button", { name: /^Revenge of the Tipping Point/ }).click();
  const peek = page.getByRole("dialog", { name: PEEK_WORK.title });
  await expect(peek).toBeVisible();
  return peek;
}

test.describe("Lights Up / Lights Down contrast", () => {
  test("foyer stays a dark room and the wordmark meets contrast", async ({ page }) => {
    await page.goto("/login");
    const heading = page.getByRole("heading", { name: "The Reading Room" });
    await expect(heading).toBeVisible();
    const foyer = await heading.evaluate((el) => {
      const root = el.closest("[data-testid='foyer']");
      if (!root) return null;
      const cs = getComputedStyle(root);
      return {
        theme: root.getAttribute("data-theme"),
        bg: cs.backgroundColor,
        text: cs.getPropertyValue("--text").trim(),
      };
    });
    expect(foyer?.theme).toBe("lights-down");
    expect(foyer?.text).toBe("#f4ead6");
    await expectReadable(heading);
    await expectReadable(page.getByText(/household's books, comics, and audiobooks/i));
  });

  test("foyer login fields paint readable value ink and Tab skips help", async ({ page }) => {
    await page.goto("/login");
    const name = page.getByRole("textbox", { name: "Name" });
    const password = page.getByLabel("Password", { exact: true });
    await expect(name).toBeVisible();
    await name.fill("owner");
    await password.fill("secret-pass");

    const nameInk = await name.evaluate((el) => {
      const cs = getComputedStyle(el);
      return {
        color: cs.color,
        fill: cs.getPropertyValue("-webkit-text-fill-color").trim() || cs.color,
        caret: cs.caretColor,
        token: cs.getPropertyValue("--text").trim(),
      };
    });
    expect(nameInk.token).toBe("#f4ead6");
    // Prefer fill when Chrome reports it; otherwise computed color.
    const inkSample = nameInk.fill && nameInk.fill !== "none" ? nameInk.fill : nameInk.color;
    expect(inkSample).toMatch(/^(?:rgb\(244,\s*234,\s*214\)|#f4ead6|rgba?\(244)/i);
    await expectReadable(name);

    const passInk = await password.evaluate((el) => {
      const cs = getComputedStyle(el);
      return cs.getPropertyValue("-webkit-text-fill-color").trim() || cs.color;
    });
    expect(passInk).toMatch(/^(?:rgb\(244,\s*234,\s*214\)|#f4ead6|rgba?\(244)/i);

    await name.focus();
    await page.keyboard.press("Tab");
    await expect(password).toBeFocused();
    await expect(page.getByRole("button", { name: "About Name" })).not.toBeFocused();
    await expect(page.getByRole("button", { name: "About Password" })).not.toBeFocused();
  });

  for (const lamp of LAMPS) {
    test.describe(lamp, () => {
      test.beforeEach(async ({ page }) => {
        await loginAsOwner(page);
        await setTheme(page, lamp);
      });

      test("Hall peek title, panel, and overflow menu are readable", async ({ page }) => {
        const peek = await openRevengePeek(page);
        expect(await backgroundAlpha(peek)).toBeGreaterThanOrEqual(0.98);
        await expectReadable(peek.getByRole("heading", { name: PEEK_WORK.title }));
        await expectReadable(peek.getByText(/Twenty-five years after/));
        const grip = peek.getByRole("button", { name: `Actions for ${PEEK_WORK.title}` });
        await expectReadable(grip);
        await grip.click();
        const menu = page.getByRole("menu", { name: `Actions for ${PEEK_WORK.title}` });
        await expect(menu).toBeVisible();
        await expectReadable(menu.getByRole("button", { name: "Favorite" }));
      });

      test("work page body type meets contrast", async ({ page }) => {
        await mockPeekHall(page);
        await page.goto(`/works/${PEEK_WORK.id}`);
        await expect(page.getByRole("heading", { name: PEEK_WORK.title })).toBeVisible();
        await expectReadable(page.getByRole("heading", { name: PEEK_WORK.title }));
        await expectReadable(page.getByText("Malcolm Gladwell").first());
        await expectReadable(page.getByText(/Twenty-five years after/));
      });

      test("Sorting heading is readable", async ({ page }) => {
        await page.goto("/review");
        const heading = page.getByRole("heading", { name: "Sorting", exact: true });
        await expect(heading).toBeVisible();
        await expectReadable(heading);
      });

      test("Settings heading and quiet-hours label are readable", async ({ page }) => {
        await page.goto("/settings");
        await expectReadable(page.getByRole("heading", { name: /Settings/i }).first());
        await page.getByRole("button", { name: "Household" }).click();
        await expectReadable(page.getByRole("heading", { name: "Quiet hours", exact: true }));
        await expectReadable(page.getByText(/Enable quiet hours/i));
      });
    });
  }
});
