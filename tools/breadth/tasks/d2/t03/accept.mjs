import assert from "node:assert/strict";
import { topoSort } from "./solution.ts";

assert.deepEqual(topoSort(0, []), [], "empty graph");
assert.deepEqual(topoSort(3, []), [0, 1, 2], "no edges is ascending order");
assert.deepEqual(topoSort(2, [[1, 0]]), [1, 0], "edge forces inversion");
assert.deepEqual(
  topoSort(4, [[3, 1], [3, 0], [1, 0], [2, 0]]),
  [2, 3, 1, 0],
  "lexicographically smallest among valid orders"
);
assert.deepEqual(
  topoSort(6, [[5, 2], [5, 0], [4, 0], [4, 1], [2, 3], [3, 1]]),
  [4, 5, 0, 2, 3, 1],
  "classic DAG, smallest-first tie-breaking"
);
assert.deepEqual(topoSort(3, [[2, 1], [2, 1]]), [0, 2, 1], "duplicate edges change nothing");
assert.deepEqual(topoSort(4, [[1, 2]]), [0, 1, 2, 3], "isolated nodes still appear");

assert.throws(() => topoSort(2, [[0, 1], [1, 0]]), Error, "two-node cycle throws");
assert.throws(() => topoSort(1, [[0, 0]]), Error, "self-loop throws");
assert.throws(() => topoSort(3, [[0, 1], [1, 2], [2, 0]]), Error, "three-node cycle throws");
assert.throws(() => topoSort(2, [[0, 2]]), Error, "endpoint out of range throws");
assert.throws(() => topoSort(2, [[0, 1.5]]), Error, "non-integer endpoint throws");
