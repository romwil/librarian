import { expect, test } from "@playwright/test";
import { E2E_OWNER, dismissWhatsNewIfPresent, loginAsOwner } from "./fixtures/auth";

test.describe("guest-ready accounts", () => {
  test("login error is announced and titles are unique", async ({ page }) => {
    await page.goto("/login");
    await expect(page).toHaveTitle(/Sign in/);
    await page.getByRole("textbox", { name: "Name" }).fill("nobody");
    await page.getByLabel("Password", { exact: true }).fill("wrong-password");
    await page.getByRole("button", { name: "Enter" }).click();
    const alert = page.getByRole("alert");
    await expect(alert).toBeVisible();
    await expect(alert).toContainText(/don't match|spelling/i);
    await page.goto("/join");
    await expect(page).toHaveTitle(/Join/);
    await expect(page.getByLabel("Invite link")).toBeVisible();
  });

  test("owner copies an absolute invite and a guest can join", async ({ page, context }) => {
    await context.grantPermissions(["clipboard-read", "clipboard-write"]);
    await loginAsOwner(page);
    await page.goto("/people");
    await expect(page.getByRole("heading", { name: "People" })).toBeVisible();
    await page.getByRole("button", { name: "Invite a reader" }).click();
    const link = page.getByText(/\/join\?token=/);
    await expect(link).toBeVisible();
    const url = (await link.textContent())?.trim() || "";
    expect(url).toMatch(/^https?:\/\//);
    expect(url).toContain("/join?token=");
    await page.getByRole("button", { name: "Copy", exact: true }).click();
    await expect(page.getByRole("status")).toContainText(/Copied/);

    await page.getByTestId("profile-menu-trigger").click();
    await page.getByTestId("logout-button").click();
    await expect(page.getByRole("heading", { name: "The Reading Room" })).toBeVisible();

    await page.goto(url);
    await expect(page.getByRole("heading", { name: "The Reading Room" })).toBeVisible();
    await expect(page.getByLabel("Password", { exact: true })).toBeVisible();
    await page.getByRole("textbox", { name: "Name" }).fill("e2e-reader");
    await page.getByLabel("Password", { exact: true }).fill("e2e-reader-ok");
    await page.getByRole("button", { name: "Enter" }).click();
    await expect(page.getByRole("heading", { name: "Hall" })).toBeVisible({ timeout: 30_000 });
    await expect(page.getByTestId("reader-welcome")).toBeVisible();
    await page.getByRole("button", { name: "Show me the Hall" }).click();
    await expect(page.getByTestId("reader-welcome")).toHaveCount(0);
  });

  test("reset link works once", async ({ page, request }) => {
    const login = await request.post("/api/auth/local/login", {
      data: { username: E2E_OWNER.username, password: E2E_OWNER.password },
    });
    expect(login.ok()).toBeTruthy();
    const minted = await request.post("/api/invites", { data: { role: "reader" } });
    const token = (await minted.json()).token as string;
    const redeemed = await request.post("/api/invites/redeem/local", {
      data: { token, username: "reset-reader", password: "old-password-1" },
    });
    expect(redeemed.ok()).toBeTruthy();
    const userId = (await redeemed.json()).user.id as string;
    const ownerLogin = await request.post("/api/auth/local/login", {
      data: { username: E2E_OWNER.username, password: E2E_OWNER.password },
    });
    expect(ownerLogin.ok()).toBeTruthy();
    const issued = await request.post(`/api/people/${userId}/reset`);
    expect(issued.ok()).toBeTruthy();
    const resetUrl = (await issued.json()).reset_url as string;
    await page.goto(resetUrl);
    await expect(page).toHaveTitle(/Reset password/);
    await page.getByRole("textbox", { name: "New password" }).fill("brand-new-pass");
    await page.getByRole("button", { name: "Set new password" }).click();
    await expect(page.getByRole("heading", { name: "Hall" })).toBeVisible({ timeout: 30_000 });
    await dismissWhatsNewIfPresent(page);
    await page.goto(resetUrl);
    await expect(page.getByRole("alert")).toContainText(/already been used|expired|missing/i);
  });
});
