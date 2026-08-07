import assert from "node:assert/strict";
import { treeDelta } from "./solution.ts";

const leaf = (name, value) => ({ name, value, children: [] });

assert.deepEqual(
  treeDelta(leaf("root", 1), leaf("root", 1)),
  [],
  "identical trees produce no ops"
);

assert.deepEqual(
  treeDelta(leaf("root", 1), leaf("root", 5)),
  [{ op: "change", path: "root", from: 1, to: 5 }],
  "root value change"
);

const beforeTree = {
  name: "r",
  value: 0,
  children: [
    { name: "a", value: 1, children: [leaf("x", 7)] },
    leaf("b", 2),
  ],
};
const afterTree = {
  name: "r",
  value: 0,
  children: [
    { name: "a", value: 1, children: [] },
    { name: "c", value: 3, children: [leaf("y", 4)] },
  ],
};
assert.deepEqual(
  treeDelta(beforeTree, afterTree),
  [
    { op: "remove", path: "r/a/x" },
    { op: "add", path: "r/c", value: 3 },
    { op: "add", path: "r/c/y", value: 4 },
    { op: "remove", path: "r/b" },
  ],
  "adds are preorder per node, removes are one per subtree"
);

assert.deepEqual(
  treeDelta(
    { name: "n", value: 1, children: [leaf("k", 2)] },
    { name: "n", value: 9, children: [leaf("k", 3), leaf("m", 4)] }
  ),
  [
    { op: "change", path: "n", from: 1, to: 9 },
    { op: "change", path: "n/k", from: 2, to: 3 },
    { op: "add", path: "n/m", value: 4 },
  ],
  "a node's change precedes its child ops"
);

assert.throws(
  () => treeDelta(leaf("a", 1), leaf("b", 1)),
  Error,
  "differing root names are rejected"
);

assert.throws(
  () =>
    treeDelta(
      { name: "r", value: 0, children: [leaf("d", 1), leaf("d", 2)] },
      leaf("r", 0)
    ),
  Error,
  "duplicate sibling names in before are rejected"
);

assert.throws(
  () =>
    treeDelta(
      leaf("r", 0),
      { name: "r", value: 0, children: [leaf("d", 1), leaf("d", 2)] }
    ),
  Error,
  "duplicate sibling names in after are rejected"
);

console.log("ok");
