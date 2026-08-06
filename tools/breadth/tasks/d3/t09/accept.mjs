import assert from "node:assert/strict";
import { topoOrder } from "./solution.ts";

assert.deepEqual(
  topoOrder(3, [[1, 0]]),
  [1, 0, 2],
  "a node released later but smaller preempts a waiting larger node",
);
assert.deepEqual(
  topoOrder(4, [[3, 0], [3, 1], [0, 2]]),
  [3, 0, 1, 2],
  "smallest-first among simultaneously available nodes",
);
assert.deepEqual(
  topoOrder(2, [[0, 1], [0, 1]]),
  [0, 1],
  "a duplicated edge is one constraint, not two",
);
assert.deepEqual(
  topoOrder(3, [[2, 1], [2, 1], [2, 1], [1, 0]]),
  [2, 1, 0],
  "a triplicated edge must not wedge the graph",
);
assert.deepEqual(
  topoOrder(6, [[5, 2], [5, 0], [4, 0], [4, 1], [2, 3], [3, 1]]),
  [4, 5, 0, 2, 3, 1],
  "layered graph resolves smallest-first at every step",
);
assert.deepEqual(topoOrder(0, []), [], "empty graph");
assert.deepEqual(topoOrder(4, []), [0, 1, 2, 3], "no edges keeps numeric order");
assert.deepEqual(topoOrder(1, []), [0], "single node");
assert.throws(() => topoOrder(2, [[0, 1], [1, 0]]), Error, "two-node cycle");
assert.throws(() => topoOrder(1, [[0, 0]]), Error, "self-loop is a cycle");
assert.throws(
  () => topoOrder(3, [[0, 1], [1, 2], [2, 1]]),
  Error,
  "cycle reached only after progress",
);
