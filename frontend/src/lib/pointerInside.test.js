import assert from "node:assert/strict";
import test from "node:test";
import { pointerEventInsideNode } from "./pointerInside.js";

function fakeRoot(members) {
  const set = new Set(members);
  const root = {
    contains(node) {
      return node === root || set.has(node);
    },
  };
  set.add(root);
  return root;
}

test("composedPath hitting the root counts as inside", () => {
  const root = fakeRoot([]);
  const event = {
    composedPath: () => [root],
    target: {},
    clientX: 0,
    clientY: 0,
  };
  assert.equal(pointerEventInsideNode(event, root, () => []), true);
});

test("contains(target) still counts when composedPath is empty", () => {
  const slider = { id: "slider" };
  const root = fakeRoot([slider]);
  const event = {
    composedPath: () => [],
    target: slider,
    clientX: 0,
    clientY: 0,
  };
  assert.equal(pointerEventInsideNode(event, root, () => []), true);
});

test("retargeted range events fall through composedPath and hit-test", () => {
  const slider = { id: "slider" };
  const label = { id: "label" };
  const chip = { id: "chip" };
  const root = fakeRoot([slider, label, chip]);
  const doc = { id: "document" };
  const event = {
    composedPath: () => [doc],
    target: doc,
    clientX: 40,
    clientY: 88,
  };
  assert.equal(
    pointerEventInsideNode(event, root, (x, y) => {
      assert.equal(x, 40);
      assert.equal(y, 88);
      return [slider];
    }),
    true,
  );
  assert.equal(pointerEventInsideNode(event, root, () => [label]), true);
  assert.equal(pointerEventInsideNode(event, root, () => [chip]), true);
});

test("a true outside click is outside", () => {
  const root = fakeRoot([]);
  const event = {
    composedPath: () => [{ id: "html" }],
    target: { id: "html" },
    clientX: 8,
    clientY: 8,
  };
  assert.equal(pointerEventInsideNode(event, root, () => [{ id: "body" }]), false);
});

test("missing root or event is outside", () => {
  assert.equal(pointerEventInsideNode(null, fakeRoot([]), () => []), false);
  assert.equal(pointerEventInsideNode({ clientX: 1, clientY: 1 }, null, () => []), false);
});
