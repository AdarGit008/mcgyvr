import assert from "node:assert/strict";
import { gaugeBuckets } from "./solution.ts";

assert.deepEqual(
  gaugeBuckets([0, 1, 2, 3, 4, 5], 0, 2, 2),
  [0, 2, 2, 2],
  "six pulses split two-two-two",
);
assert.deepEqual(
  gaugeBuckets([-3, -1, 0], 0, 2, 1),
  [2, 1, 0],
  "pulses under the base are counted, never dropped",
);
assert.deepEqual(
  gaugeBuckets([5], 0, 5, 2),
  [0, 0, 1, 0],
  "a pulse on a shared edge belongs to the higher pocket",
);
assert.deepEqual(
  gaugeBuckets([6], 0, 10, 2),
  [0, 1, 0, 0],
  "position inside a pocket is found by its floor, not the nearest edge",
);
assert.deepEqual(
  gaugeBuckets([20, 47], 0, 10, 2),
  [0, 0, 0, 2],
  "a pulse at or past the top edge is overflow, not the last pocket",
);
assert.deepEqual(
  gaugeBuckets([-10, -1, 9, 10], -10, 5, 4),
  [0, 1, 1, 0, 1, 1],
  "a negative base shifts every pocket",
);
assert.deepEqual(gaugeBuckets([], 3, 4, 3), [0, 0, 0, 0, 0], "no pulses, all zero");
console.log("ok");
