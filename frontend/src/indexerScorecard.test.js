import assert from "node:assert/strict";
import { describe, it } from "vitest";
import {
  formatMatchPercent,
  kindStatLabel,
  lanternPresence,
  lanternStatsModel,
  lanternWeather,
  scorecardLanterns,
  scorecardPresence,
} from "./lib/indexerScorecard.js";
import { readStyles } from "./test/styles.js";

const stylesSrc = readStyles();

function hexToRgb(hex) {
  const h = hex.replace("#", "");
  return {
    r: parseInt(h.slice(0, 2), 16),
    g: parseInt(h.slice(2, 4), 16),
    b: parseInt(h.slice(4, 6), 16),
  };
}

function relativeLuminance({ r, g, b }) {
  const channel = (value) => {
    const v = value / 255;
    return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
}

function contrastRatio(foreground, background) {
  const lighter = Math.max(relativeLuminance(hexToRgb(foreground)), relativeLuminance(hexToRgb(background)));
  const darker = Math.min(relativeLuminance(hexToRgb(foreground)), relativeLuminance(hexToRgb(background)));
  return (lighter + 0.05) / (darker + 0.05);
}

describe("indexerScorecard", () => {
  it("maps lantern weather without inventing grades", () => {
    assert.equal(lanternWeather({ weather: "bright" }), "bright");
    assert.equal(lanternWeather({ weather: "dark" }), "dark");
    assert.equal(lanternWeather({ muted: true }), "muted");
    assert.equal(lanternWeather({ weather: "<script>" }), "idle");
    assert.equal(lanternWeather(null), "idle");
  });

  it("prefers server presence and stays warm on hostile payloads", () => {
    assert.equal(lanternPresence({ presence: "NZBFinder burns steady." }), "NZBFinder burns steady.");
    assert.match(lanternPresence({ weather: "muted", name: "Host A" }), /rests muted/);
    assert.match(lanternPresence({ weather: "dark", name: "Host B" }), /went dark/);
    assert.equal(scorecardPresence({ presence: "The Find lanterns burn steady." }), "The Find lanterns burn steady.");
    assert.match(scorecardPresence({}), /wait for the next Find/);
    assert.deepEqual(scorecardLanterns({ lanterns: [{ id: "a" }] }), [{ id: "a" }]);
    assert.deepEqual(scorecardLanterns({ lanterns: "nope" }), []);
  });

  it("keeps lantern copy readable in both themes without beige-on-beige", () => {
    assert.match(stylesSrc, /\.indexer-scorecard\s*\{[\s\S]*?--lantern-card:/);
    assert.match(stylesSrc, /\.indexer-scorecard\s*\{[\s\S]*?--lantern-note:\s*var\(--muted\)/);
    const lightsDown = stylesSrc.match(
      /html\[data-theme="lights-down"\]\s+\.indexer-scorecard\s*\{[^}]+\}/,
    );
    assert.ok(lightsDown, "lights-down remaps lantern card tokens");
    assert.match(lightsDown[0], /--lantern-card:/);
    assert.match(lightsDown[0], /--surface-raised/);
    assert.doesNotMatch(lightsDown[0], /--paper/);
    assert.match(stylesSrc, /\.indexer-lantern-name\s*\{[\s\S]*?color:\s*var\(--lantern-ink\)/);
    assert.match(stylesSrc, /\.indexer-lantern-presence\s*\{[\s\S]*?color:\s*var\(--lantern-note\)/);
    assert.match(stylesSrc, /\.indexer-lantern-idle\s+\.indexer-lantern-flame/);
    assert.match(
      stylesSrc,
      /html\[data-theme="lights-down"\]\s+\.grooming-undo\s*\{[\s\S]*?--surface-raised/,
    );
    // Documented token pairs from live Automat measurement (raised leather vs cream ink / warm note).
    assert.ok(contrastRatio("#f4ead6", "#281f17") >= 7, "lights-down names meet AAA");
    assert.ok(contrastRatio("#dccfb9", "#281f17") >= 7, "lights-down presence meets AAA");
    assert.ok(contrastRatio("#1c1612", "#f6f0e6") >= 7, "lights-up names stay dark-on-paper");
    assert.ok(contrastRatio("#3a322c", "#f6f0e6") >= 7, "lights-up presence stays ink-on-paper");
  });

  it("formats match rate chips without a number dump", () => {
    assert.equal(formatMatchPercent(0.8), "80%");
    assert.equal(formatMatchPercent(0), "0%");
    assert.equal(formatMatchPercent(null), "—");
    assert.equal(formatMatchPercent("<script>"), "—");
    assert.equal(kindStatLabel("book"), "Books");
    assert.equal(kindStatLabel("audiobook"), "Audiobooks");
    assert.equal(kindStatLabel("not-a-kind"), "Any");
    assert.equal(lanternStatsModel({}), null);
    assert.equal(lanternStatsModel({ stats: { searches: 0 } }), null);

    const model = lanternStatsModel(
      {
        stats: {
          searches: 10,
          hits: 6,
          empty: 2,
          errors: 2,
          rate_limited: 1,
          by_kind: [
            { kind: "book", searches: 8, hits: 6, empty: 2, errors: 0, rate_limited: 0 },
            { kind: "movie", searches: 4, hits: 1, empty: 3, errors: 0, rate_limited: 0 },
            { kind: "<script>", searches: 9, hits: 9, empty: 0 },
          ],
        },
      },
      { showExtra: false },
    );
    assert.equal(model.percent, "75%");
    assert.equal(model.spokenLabel, "8 spoken");
    assert.match(model.notes, /2 empty/);
    assert.match(model.notes, /1 rate limit/);
    assert.deepEqual(
      model.kinds.map((row) => row.label),
      ["Books"],
    );
    assert.equal(model.kinds[0].percent, "75%");
    assert.equal(model.kinds[0].fill, 75);

    const withExtra = lanternStatsModel(
      {
        stats: {
          searches: 4,
          hits: 1,
          empty: 3,
          errors: 0,
          rate_limited: 0,
          by_kind: [{ kind: "movie", searches: 4, hits: 1, empty: 3 }],
        },
      },
      { showExtra: true },
    );
    assert.deepEqual(withExtra.kinds, []);
  });
});
