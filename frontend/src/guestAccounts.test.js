import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { test } from "vitest";

const root = dirname(fileURLToPath(import.meta.url));
const peopleSrc = readFileSync(join(root, "pages/PeoplePage.jsx"), "utf8");
const loginSrc = readFileSync(join(root, "pages/LoginPage.jsx"), "utf8");
const joinSrc = readFileSync(join(root, "pages/JoinPage.jsx"), "utf8");
const cardSrc = readFileSync(join(root, "pages/CardPage.jsx"), "utf8");
const menuSrc = readFileSync(join(root, "components/ProfileMenu.jsx"), "utf8");

test("People has Copy, pending revoke, and a helper invite for the owner", () => {
  assert.match(peopleSrc, />\s*Copy\s*</);
  assert.match(peopleSrc, /Revoke/);
  assert.match(peopleSrc, /INVITE_OP_LABEL/);
  assert.match(peopleSrc, /Pending invites/);
  assert.doesNotMatch(peopleSrc, /Place a hold/);
});

test("foyer announces errors, pastes a token, and shows the password", () => {
  assert.match(loginSrc, /role="alert"/);
  assert.match(loginSrc, /FOYER_PASTE_LABEL/);
  assert.match(loginSrc, /PasswordField/);
  assert.match(joinSrc, /autoComplete="username"/);
  assert.match(joinSrc, /autoComplete="new-password"/);
  assert.match(joinSrc, /PAGE_TITLE_JOIN/);
});

test("Library card hosts Privacy and Account, and ops can open People", () => {
  assert.match(cardSrc, /privacy-panel/);
  assert.match(cardSrc, /EXPORT_MY_CARD/);
  assert.match(cardSrc, /SIGN_OUT_EVERYWHERE/);
  assert.match(menuSrc, /\{op \? \(/);
  assert.match(menuSrc, />\s*People\s*</);
});
