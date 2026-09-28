import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  lanternPresence,
  lanternWeather,
  scorecardLanterns,
  scorecardPresence,
} from "./lib/indexerScorecard.js";

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
});
