import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  annotateChasedGaps,
  buildGapChaseQueries,
  defaultPartSelectionKeys,
  formatBytes,
  GAP_CHASE_QUERY_CAP,
  groupBeyondItems,
  mergeBeyondHits,
  missingParts,
  normalizePartBase,
  parsePartMarker,
  partBeadStates,
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

  it("strips bare N/M yEnc indexes so Part N/M bases match", () => {
    // [._]+ collapses the abbreviation dot in "E." — same as other strip paths.
    assert.equal(
      stripPartMarkers("Raymond E. Feist - Magician Part 3/5 13/16.mp3 yEnc"),
      "Raymond E Feist - Magician",
    );
    assert.equal(
      normalizePartBase("Raymond E. Feist - Magician Part 3/5 13/16.mp3 yEnc"),
      normalizePartBase("Raymond E. Feist - Magician Part 5/5 15/16.mp3 yEnc"),
    );
    // Bare N/M alone is not a part marker.
    assert.equal(parsePartMarker("Raymond E. Feist - Magician 13/16.mp3"), null);
  });

  it("prefers Part N/M over yEnc [N/M] when both present", () => {
    assert.deepEqual(
      parsePartMarker('(NMRT [13/16] - "Raymond E. Feist - Magician Part 3/5.mp3" yEnc'),
      { part: 3, total: 5, style: "part", raw: "Part 3/5" },
    );
    assert.deepEqual(
      parsePartMarker("(NMRT [13/16] - Magician 03of05 yEnc"),
      { part: 3, total: 5, style: "of", raw: "03of05" },
    );
    // Bracket-only titles still parse as bracket.
    assert.deepEqual(parsePartMarker('(NMRT [01/44] - "Tin Can Sailors.par2" yEnc'), {
      part: 1,
      total: 44,
      style: "bracket",
      raw: "[01/44]",
    });
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

  it("groups Feist Part 3–5/5 despite bare yEnc 13/16–15/16 indexes", () => {
    const items = [
      {
        title: "Raymond E. Feist - Magician Part 3/5 13/16.mp3 yEnc",
        guid: "f3",
        size: 100,
        host_name: "NZBFinder",
        kind: "audiobook",
      },
      {
        title: "Raymond E. Feist - Magician Part 4/5 14/16.mp3 yEnc",
        guid: "f4",
        size: 100,
        host_name: "NZBFinder",
        kind: "audiobook",
      },
      {
        title: "Raymond E. Feist - Magician Part 5/5 15/16.mp3 yEnc",
        guid: "f5",
        size: 100,
        host_name: "NZBFinder",
        kind: "audiobook",
      },
    ];
    const { sets, singles } = groupBeyondItems(items);
    assert.equal(sets.length, 1);
    assert.equal(singles.length, 0);
    const feist = sets[0];
    assert.equal(feist.total, 5);
    assert.equal(feist.found, 3);
    assert.deepEqual(
      feist.parts.map((p) => p.part),
      [3, 4, 5],
    );
    assert.deepEqual(feist.missing, [1, 2]);
    assert.equal(feist.complete, false);
    assert.equal(partSetStatusLine(feist), "3/5 · incomplete · missing 2");
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


describe("multipart gap chase", () => {
  it("builds capped Part/of/CD queries for missing numbers", () => {
    const set = {
      title: "Raymond E. Feist - Magician",
      total: 5,
      style: "part",
      complete: false,
      missing: [1, 2],
    };
    const queries = buildGapChaseQueries(set, { cap: 5 });
    assert.ok(queries.length <= 5);
    assert.ok(queries.some((q) => /Part 1\/5/.test(q)));
    assert.ok(queries.some((q) => /Part 2/.test(q)));
    assert.ok(buildGapChaseQueries(set, { cap: GAP_CHASE_QUERY_CAP }).length <= GAP_CHASE_QUERY_CAP);
  });

  it("merges chase hits and annotates Request missing", () => {
    const existing = [{ guid: "f3", title: "Magician Part 3/5" }];
    const incoming = [
      { guid: "f3", title: "Magician Part 3/5" },
      { guid: "f1", title: "Raymond E. Feist - Magician Part 1/5" },
    ];
    const merged = mergeBeyondHits(existing, incoming);
    assert.equal(merged.added, 1);
    assert.equal(merged.items.length, 2);

    const set = {
      complete: false,
      found: 2,
      missing: [2],
      parts: [
        { part: 1, item: { guid: "f1" } },
        { part: 3, item: { guid: "f3" } },
      ],
      missingItems: [],
    };
    const annotated = annotateChasedGaps(set, [1, 2]);
    assert.deepEqual(
      annotated.missingItems.map((row) => row.guid),
      ["f1"],
    );
    const action = partSetRequestAction({ ...annotated, chaseQueriesTried: 3 }, 1);
    assert.equal(action.kind, "missing-listed");
    assert.equal(action.label, "Request missing (1)");
  });

  it("mentions tried queries when gaps stay unlisted", () => {
    const action = partSetRequestAction(
      { complete: false, found: 1, missing: [2, 3], missingItems: [], parts: [{ part: 1 }], chaseQueriesTried: 4 },
      1,
    );
    assert.equal(action.kind, "listed-only");
    assert.match(action.honesty, /Tried 4 queries/);
  });

  it("builds bead states for found/missing parts", () => {
    const beads = partBeadStates({
      total: 4,
      parts: [{ part: 1 }, { part: 3 }],
    });
    assert.deepEqual(
      beads.map((b) => b.state),
      ["found", "missing", "found", "missing"],
    );
  });
});
