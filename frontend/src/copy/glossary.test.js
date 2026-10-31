import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { test } from "vitest";
import { GLOSSARY, glossaryForRole, glossaryMarkdownTable } from "./glossary.js";

const root = dirname(fileURLToPath(import.meta.url));
const helpMd = readFileSync(join(root, "../../../docs/HELP.md"), "utf8");
const helpPage = readFileSync(join(root, "../pages/HelpPage.jsx"), "utf8");
const menuSrc = readFileSync(join(root, "../components/ProfileMenu.jsx"), "utf8");
const mainSrc = readFileSync(join(root, "../main.jsx"), "utf8");

test("reader glossary is a subset and HELP.md lists every term", () => {
  const reader = glossaryForRole("reader");
  const owner = glossaryForRole("owner");
  assert.ok(reader.length >= 8);
  assert.ok(owner.length > reader.length);
  assert.equal(owner.length, GLOSSARY.length);
  assert.ok(reader.every((row) => row.audience === "reader"));
  for (const row of GLOSSARY) {
    assert.match(helpMd, new RegExp(`\\*\\*${row.term}\\*\\*`));
  }
  assert.match(glossaryMarkdownTable(), /\*\*Sorting\*\*/);
});

test("Help is routed and linked from the Library card menu", () => {
  assert.match(mainSrc, /path="help"/);
  assert.match(helpPage, /help-page/);
  assert.match(menuSrc, /to="\/help"/);
});
