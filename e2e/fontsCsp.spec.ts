import { expect, test } from "@playwright/test";

test.describe("fonts and CSP", () => {
  test("login never talks to Google Fonts and sends a CSP", async ({ page }) => {
    const remoteFonts: string[] = [];
    page.on("request", (request) => {
      const url = request.url();
      if (url.includes("fonts.googleapis.com") || url.includes("fonts.gstatic.com")) {
        remoteFonts.push(url);
      }
    });
    const response = await page.goto("/login");
    expect(response, "login document").toBeTruthy();
    const csp = response?.headers()["content-security-policy"] || "";
    expect(csp).toContain("script-src 'self'");
    expect(csp).toContain("frame-ancestors 'none'");
    expect(csp).not.toContain("fonts.googleapis.com");
    expect(csp).not.toContain("fonts.gstatic.com");
    expect(response?.headers()["x-content-type-options"]).toBe("nosniff");
    await expect(page.getByRole("heading", { name: "The Reading Room" })).toBeVisible();
    expect(remoteFonts).toEqual([]);
    const inlineScripts = await page.locator("script:not([src])").count();
    expect(inlineScripts).toBe(0);
    const googleLinks = await page.locator('link[href*="fonts.google"]').count();
    expect(googleLinks).toBe(0);
    await page.evaluate(() => document.fonts.ready);
    const loaded = await page.evaluate(() => {
      const faces = [...document.fonts].map((face) => face.family);
      return {
        literata: document.fonts.check("16px Literata") || faces.includes("Literata"),
        sourceSans: document.fonts.check('16px "Source Sans 3"') || faces.includes("Source Sans 3"),
        faces,
      };
    });
    expect(loaded.literata || loaded.sourceSans, JSON.stringify(loaded.faces)).toBeTruthy();
  });
});
