import { expect, test } from "@playwright/test";
import { loginAsOwner } from "./fixtures/auth";

test.describe("health / shell", () => {
  test("API health is ok", async ({ request }) => {
    const res = await request.get("/api/health");
    expect(res.ok()).toBeTruthy();
    const body = await res.json();
    expect(body.status).toBe("ok");
  });

  test("login shell then Hall after owner enter", async ({ page }) => {
    await page.goto("/login");
    await expect(page.getByTestId("foyer")).toBeVisible();
    await expect(page.getByRole("heading", { name: "The Reading Room" })).toBeVisible();
    await loginAsOwner(page);
    await expect(page.getByTestId("hall")).toBeVisible();
    await expect(page.getByRole("link", { name: "Hall" }).first()).toBeVisible();
  });
});
