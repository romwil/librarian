import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { wantedDeskModel } from "./wantedDesk.js";

const items = [
  {
    id: "w-miss",
    work_id: "book-1",
    title: "Circe",
    author: "Madeline Miller",
    kind: "audiobook",
    status: "wanted",
  },
  {
    id: "w-hand",
    title: "Piranesi",
    author: "Susanna Clarke",
    kind: "book",
    status: "asked",
  },
  {
    id: "w-gone",
    title: "Dismissed",
    kind: "audiobook",
    status: "dismissed",
  },
];

describe("Wanted desk", () => {
  it("lists companion misses and hand-added titles, not dismissed rows", () => {
    const desk = wantedDeskModel({ items, role: "reader" });
    assert.deepEqual(
      desk.rows.map((row) => row.title),
      ["Circe", "Piranesi"],
    );
    assert.equal(desk.rows[0].workId, "book-1");
    assert.equal(desk.rows[0].statusLabel, "Wanted");
    assert.equal(desk.rows[1].statusLabel, "Asked");
    assert.match(desk.rows[0].searchHref, /kind=audiobook/);
    assert.match(desk.rows[0].searchHref, /title=Circe/);
    assert.match(desk.rows[1].findHref, /kind=book/);
    assert.match(desk.rows[1].findHref, /title=Piranesi/);
    assert.equal(desk.empty, false);
  });

  it("keeps add and dismiss with the owner and op", () => {
    const reader = wantedDeskModel({ items, role: "reader" });
    assert.equal(reader.canAdd, false);
    assert.equal(reader.rows.every((row) => row.canDismiss === false), true);

    const owner = wantedDeskModel({ items, role: "owner" });
    assert.equal(owner.canAdd, true);
    assert.equal(owner.rows[0].canDismiss, true);

    const op = wantedDeskModel({ items, role: "op" });
    assert.equal(op.canAdd, true);
    assert.equal(op.rows[1].canDismiss, true);
  });

  it("is empty when nothing is still wanted", () => {
    const desk = wantedDeskModel({ items: [{ id: "x", title: "Gone", status: "dismissed" }], role: "owner" });
    assert.equal(desk.empty, true);
    assert.equal(desk.canAdd, true);
    assert.deepEqual(desk.rows, []);
  });
});
