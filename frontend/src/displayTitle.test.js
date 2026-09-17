import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  displayPrimaryTitle,
  displayTitleParts,
  isAllCapsImprint,
  shouldDemotePublisherPrefix,
} from "./displayTitle.js";

describe("displayTitle publisher demotion", () => {
  it("demotes ALL-CAPS comic imprints so the series leads", () => {
    const parts = displayTitleParts("TOKYOPOP - Monster And Ghost Vol 03", { kind: "comic" });
    assert.equal(parts.primary, "Monster And Ghost Vol 03");
    assert.equal(parts.secondary, "TokyoPop");
    assert.match(parts.raw, /TOKYOPOP/);
    assert.equal(parts.full, "Monster And Ghost Vol 03 · TokyoPop");
  });

  it("demotes IMAGE COMICS and Title-Case known publishers", () => {
    assert.equal(
      displayPrimaryTitle("IMAGE COMICS - Witchblade Compendium Vol 01", { kind: "comic" }),
      "Witchblade Compendium Vol 01",
    );
    assert.equal(displayTitleParts("IMAGE COMICS - Witchblade", { kind: "comic" }).secondary, "Image Comics");
    assert.equal(
      displayPrimaryTitle("Dynamite - Aladdin No 03 2026", { kind: "comic" }),
      "Aladdin No 03 2026",
    );
    assert.equal(displayTitleParts("Dark Horse - Concrete Vol 1", { kind: "comic" }).secondary, "Dark Horse");
  });

  it("handles en/em dashes the same as hyphen", () => {
    assert.equal(displayPrimaryTitle("Marvel – Daredevil #01", { kind: "comic" }), "Daredevil #01");
    assert.equal(displayPrimaryTitle("IDW — Locke & Key", { kind: "comic" }), "Locke & Key");
  });

  it("demotes imprint-suffix comics without a known-list hit", () => {
    const parts = displayTitleParts("Aftershock Comics - Undiscovered Country 01", { kind: "comic" });
    assert.equal(parts.primary, "Undiscovered Country 01");
    assert.match(parts.secondary, /Aftershock/i);
  });

  it("keeps Author - Title for books and audiobooks", () => {
    assert.equal(
      displayPrimaryTitle("Raymond E. Feist - Magician", { kind: "book" }),
      "Raymond E. Feist - Magician",
    );
    assert.equal(
      displayPrimaryTitle("Raymond E. Feist - Magician", { kind: "audiobook" }),
      "Raymond E. Feist - Magician",
    );
    assert.equal(
      displayPrimaryTitle("Stephen King - The Stand", { kind: "book" }),
      "Stephen King - The Stand",
    );
    assert.equal(displayTitleParts("Raymond E. Feist - Magician", { kind: "book" }).secondary, "");
  });

  it("does not demote comic creators with middle initials", () => {
    assert.equal(
      displayPrimaryTitle("Brian K. Vaughan - Saga", { kind: "comic" }),
      "Brian K. Vaughan - Saga",
    );
  });

  it("does not demote Title-Case series that are not imprints", () => {
    assert.equal(displayPrimaryTitle("Batman - Year One", { kind: "comic" }), "Batman - Year One");
    assert.equal(displayPrimaryTitle("Piranesi", { kind: "book" }), "Piranesi");
  });

  it("strips bare yEnc N/M markers from the display primary", () => {
    const parts = displayTitleParts("TOKYOPOP - Monster And Ghost 03/16.mp3 yEnc", { kind: "comic" });
    assert.equal(parts.primary, "Monster And Ghost");
    assert.equal(parts.secondary, "TokyoPop");
  });

  it("classifies ALL-CAPS imprint segments", () => {
    assert.equal(isAllCapsImprint("TOKYOPOP"), true);
    assert.equal(isAllCapsImprint("IMAGE COMICS"), true);
    assert.equal(isAllCapsImprint("TokyoPop"), false);
    assert.equal(isAllCapsImprint("Raymond E. Feist"), false);
  });

  it("only demotes book prefixes when the left side is a known publisher", () => {
    assert.equal(shouldDemotePublisherPrefix("TOKYOPOP", { kind: "book" }), true);
    assert.equal(shouldDemotePublisherPrefix("STEPHEN KING", { kind: "book" }), false);
    assert.equal(shouldDemotePublisherPrefix("Image Comics", { kind: "comic" }), true);
  });
});
