import assert from "node:assert/strict";
import test from "node:test";
import {
  finishRitualCopy,
  hallLampPeriod,
  hallLampPeriodLabel,
  welcomeBackCopy,
} from "./lampRituals.js";

function atHour(hour) {
  return new Date(2026, 8, 25, hour, 0, 0);
}

test("hallLampPeriod maps local hours to dawn/day/dusk/night", () => {
  assert.equal(hallLampPeriod(atHour(5)), "dawn");
  assert.equal(hallLampPeriod(atHour(7)), "dawn");
  assert.equal(hallLampPeriod(atHour(8)), "day");
  assert.equal(hallLampPeriod(atHour(16)), "day");
  assert.equal(hallLampPeriod(atHour(17)), "dusk");
  assert.equal(hallLampPeriod(atHour(20)), "dusk");
  assert.equal(hallLampPeriod(atHour(21)), "night");
  assert.equal(hallLampPeriod(atHour(3)), "night");
});

test("hallLampPeriodLabel speaks library periods", () => {
  assert.equal(hallLampPeriodLabel("dawn"), "Dawn in the Hall");
  assert.equal(hallLampPeriodLabel("dusk"), "Dusk in the Hall");
  assert.equal(hallLampPeriodLabel("night"), "Night in the Hall");
  assert.equal(hallLampPeriodLabel("day"), "Day in the Hall");
});

test("welcomeBackCopy is empty when nothing waits", () => {
  assert.equal(welcomeBackCopy({ continueCount: 0, listeningCount: 0 }), "");
  assert.equal(welcomeBackCopy({}), "");
});

test("welcomeBackCopy greets when Continue waits", () => {
  assert.match(welcomeBackCopy({ continueCount: 1, period: "day" }), /Welcome back/);
  assert.match(welcomeBackCopy({ listeningCount: 2, period: "dawn" }), /early pages/);
  assert.match(welcomeBackCopy({ continueCount: 1, period: "dusk" }), /evening lamp/);
  assert.match(welcomeBackCopy({ continueCount: 1, period: "night" }), /still warm/);
});

test("finishRitualCopy is a quiet ceremony line", () => {
  assert.equal(finishRitualCopy(), "The lamp remembers.");
});
