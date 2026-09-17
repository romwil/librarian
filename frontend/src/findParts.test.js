import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  defaultPartSelectionKeys,
  formatBytes,
  groupBeyondItems,
  missingParts,
  normalizePartBase,
  parsePartMarker,
  partIndexOrigin,
  partSetFingerprint,
  partSetRequestAction,
  partSetStatusLine,
  stripPartMarkers,
} from "./findParts.js";

describe("multipart Find parsing", () => {
  it("parses NofM, Part/CD/Disc, and bracket markers", () => {
    assert.deepEqual(parsePartMarker("Stephen King - The Stand 01of32"), {
      part: 1,
      total: 32,
      style: "of",
      raw: "01of32",
    });
    assert.deepEqual(parsePartMarker("Title Part 3 of 10"), {
      part: 3,
      total: 10,
      style: "of",
      raw: "3 of 10",
    });
    assert.deepEqual(parsePartMarker("Title Part 7"), {
      part: 7,
      total: null,
      style: "part",
      raw: "Part 7",
    });
    assert.deepEqual(parsePartMarker("Album CD2"), {
      part: 2,
      total: null,
      style: "cd",
      raw: "CD2",
    });
    assert.deepEqual(parsePartMarker("Book Disc 1/4"), {
      part: 1,
      total: 4,
      style: "disc",
      raw: "Disc 1/4",
    });
    assert.deepEqual(parsePartMarker('(NMRT [01/44] - "Tin Can Sailors.par2" yEnc'), {
      part: 1,
      total: 44,
      style: "bracket",
      raw: "[01/44]",
    });
    assert.deepEqual(parsePartMarker("Album 00of04"), {
      part: 0,
      total: 4,
      style: "of",
      raw: "00of04",
    });
    assert.equal(parsePartMarker("Stephen King - The Stand"), null);
  });

  it("strips markers for a stable base title", () => {
    assert.equal(stripPartMarkers("attn abigail Stephen King - The Stand 01of32.mp3 yEnc"), "attn abigail Stephen King - The Stand");
    assert.equal(normalizePartBase("attn abigail Stephen King - The Stand 23of32.mp3"), "stephen king the stand");
    assert.equal(
      normalizePartBase("attn abigail Stephen King - The Stand 01of32"),
      normalizePartBase("attn abigail Stephen King - The Stand 02of32.mp3 yEnc"),
    );
  });

  it("fingerprints same release across parts", () => {
    const a = { title: "Stephen King - The Stand 01of32", host_name: "NZBFinder" };
    const b = { title: "Stephen King - The Stand 23of32.mp3", host_name: "NZBFinder" };
    assert.equal(partSetFingerprint(a), partSetFingerprint(b));
    assert.notEqual(
      partSetFingerprint(a),
      partSetFingerprint({ title: "Other Book 01of32", host_name: "NZBFinder" }),
    );
  });

  it("groups The Stand parts and leaves unrelated singles", () => {
    const items = [
      { title: "attn abigail Stephen King - The Stand 01of32", guid: "g1", size: 100, host_name: "NZBFinder", kind: "audiobook" },
      { title: "attn abigail Stephen King - The Stand 23of32.mp3", guid: "g23", size: 90, host_name: "NZBFinder", kind: "audiobook" },
      { title: "attn abigail Stephen King - The Stand 01of32.mp3", guid: "g1b", size: 110, host_name: "NZBFinder", kind: "audiobook" },
      { title: "attn abigail Stephen King - The Stand 02of32.mp3 yEnc", guid: "g2", size: 95, host_name: "NZBFinder", kind: "audiobook" },
      { title: "Oliver Burkeman - The Antidote", guid: "gx", host_name: "NZBFinder", kind: "audiobook" },
      { title: '(NMRT [01/44] - "Tin Can Sailors.par2" yEnc', guid: "t1", host_name: "NZBFinder", kind: "audiobook" },
    ];
    const { sets, singles } = groupBeyondItems(items);
    assert.equal(sets.length, 2);
    const stand = sets.find((row) => row.total === 32);
    assert.ok(stand);
    assert.equal(stand.found, 3);
    assert.equal(stand.complete, false);
    assert.equal(stand.missing.length, 29);
    assert.deepEqual(
      stand.parts.map((p) => p.part),
      [1, 2, 23],
    );
    assert.equal(stand.parts[0].item.guid, "g1b");
    assert.equal(stand.parts[0].alternatives.length, 1);
    assert.equal(partSetStatusLine(stand), "3/32 · incomplete · missing 29");
    const tin = sets.find((row) => row.total === 44);
    assert.ok(tin);
    assert.equal(tin.found, 1);
    assert.equal(singles.length, 1);
    assert.equal(singles[0].guid, "gx");
  });

  it("groups when only one part of a known total is present", () => {
    const { sets, singles } = groupBeyondItems([
      { title: "Saga #54 Part 1 of 2", guid: "c1", host_name: "NZBFinder", kind: "comic" },
    ]);
    assert.equal(sets.length, 1);
    assert.equal(sets[0].found, 1);
    assert.equal(sets[0].total, 2);
    assert.equal(sets[0].complete, false);
    assert.equal(singles.length, 0);
  });

  it("treats part 00 as 0-based so 1/4 is missing 3 not 4", () => {
    assert.equal(partIndexOrigin([{ part: 0 }]), 0);
    assert.equal(partIndexOrigin([{ part: 1 }]), 1);
    assert.deepEqual(missingParts([{ part: 0 }], 4), [1, 2, 3]);
    assert.deepEqual(missingParts([{ part: 1 }], 4), [2, 3, 4]);
    assert.deepEqual(missingParts([{ part: 0 }, { part: 1 }, { part: 2 }, { part: 3 }], 4), []);

    const { sets } = groupBeyondItems([
      { title: "Sample Pack 00of04", guid: "z0", host_name: "NZBFinder", kind: "audiobook" },
    ]);
    assert.equal(sets.length, 1);
    assert.equal(sets[0].found, 1);
    assert.equal(sets[0].total, 4);
    assert.deepEqual(sets[0].missing, [1, 2, 3]);
    assert.equal(partSetStatusLine(sets[0]), "1/4 · incomplete · missing 3");
  });

  it("formats sizes for the part grid", () => {
    assert.equal(formatBytes(0), "");
    assert.equal(formatBytes(2048), "2.0 KB");
    assert.equal(formatBytes(5 * 1024 * 1024), "5.0 MB");
  });
});

describe("multipart request CTA policy", () => {
  it("defaults to selecting all only when the set is complete", () => {
    const complete = {
      complete: true,
      found: 2,
      missing: [],
      missingItems: [],
      parts: [
        { part: 1, item: { guid: "a" } },
        { part: 2, item: { guid: "b" } },
      ],
    };
    assert.deepEqual(defaultPartSelectionKeys(complete), ["a", "b"]);

    const incomplete = {
      complete: false,
      found: 3,
      missing: [3, 4, 5],
      missingItems: [],
      parts: [
        { part: 1, item: { guid: "g1" } },
        { part: 2, item: { guid: "g2" } },
        { part: 23, item: { guid: "g23" } },
      ],
    };
    assert.deepEqual(defaultPartSelectionKeys(incomplete), []);
  });

  it("uses secondary Request listed when gaps have no guids", () => {
    const stand = {
      complete: false,
      found: 3,
      missing: Array.from({ length: 32 }, (_, i) => i + 1).filter((n) => ![1, 2, 23].includes(n)),
      missingItems: [],
      parts: [{ part: 1 }, { part: 2 }, { part: 23 }],
    };
    assert.equal(stand.missing.length, 29);
    const idle = partSetRequestAction(stand, 0);
    assert.equal(idle.kind, "listed-only");
    assert.equal(idle.style, "secondary");
    assert.equal(idle.label, "Request listed");
    assert.equal(idle.enabled, false);
    assert.match(idle.honesty, /Missing 29 parts aren’t listed/);

    const selected = partSetRequestAction(stand, 3);
    assert.equal(selected.label, "Request listed (3)");
    assert.equal(selected.enabled, true);
    assert.equal(selected.style, "secondary");
  });

  it("uses primary Request complete set when whole set is listed", () => {
    const set = { complete: true, found: 4, missing: [], missingItems: [], parts: [1, 2, 3, 4] };
    const all = partSetRequestAction(set, 4);
    assert.equal(all.kind, "complete");
    assert.equal(all.style, "primary");
    assert.equal(all.label, "Request complete set");
    assert.equal(all.honesty, "");

    const partial = partSetRequestAction(set, 2);
    assert.equal(partial.label, "Request listed (2)");
  });

  it("prefers Request missing when gap NZBs are listed", () => {
    const set = {
      complete: false,
      found: 1,
      missing: [2],
      missingItems: [{ guid: "gap2", title: "Part 2" }],
      parts: [{ part: 1, item: { guid: "g1" } }],
    };
    assert.deepEqual(defaultPartSelectionKeys(set), ["gap2"]);
    const action = partSetRequestAction(set, 1);
    assert.equal(action.kind, "missing-listed");
    assert.equal(action.style, "primary");
    assert.equal(action.label, "Request missing (1)");
    assert.equal(action.honesty, "");
  });
});
