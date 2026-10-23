import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  DRUNKENSLUG_PRESET,
  addIndexerPreset,
  extraIndexerRowFromPreset,
  extraIndexersHavePreset,
} from "./indexerPresets.js";

describe("indexer presets", () => {
  it("fills a DrunkenSlug row without a token", () => {
    const row = extraIndexerRowFromPreset(DRUNKENSLUG_PRESET);
    assert.equal(row.id, "drunkenslug");
    assert.equal(row.name, "DrunkenSlug");
    assert.equal(row.url, "https://drunkenslug.com");
    assert.equal(row.api_token, "");
    assert.equal(row.enabled, true);
    assert.equal(row.dialect, "newznab");
    assert.doesNotMatch(JSON.stringify(row), /prowlarr/i);
  });

  it("adds DrunkenSlug once, matching id or URL", () => {
    const first = addIndexerPreset([], DRUNKENSLUG_PRESET);
    assert.equal(first.length, 1);
    assert.equal(addIndexerPreset(first, DRUNKENSLUG_PRESET).length, 1);
    assert.equal(
      extraIndexersHavePreset([{ id: "x", name: "Other", url: "https://drunkenslug.com/" }], DRUNKENSLUG_PRESET),
      true,
    );
  });
});
