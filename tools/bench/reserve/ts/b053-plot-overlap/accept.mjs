import assert from "node:assert/strict";
import { plotOverlap } from "./solution.ts";

assert.equal(plotOverlap([0, 0, 4, 4], [2, 1, 6, 5]), 6, "partial overlap");
assert.equal(plotOverlap([0, 0, 10, 10], [2, 3, 5, 7]), 12, "a contained plot");
assert.equal(plotOverlap([0, 0, 4, 3], [0, 0, 4, 3]), 12, "identical plots share everything");
assert.equal(plotOverlap([0, 0, 2, 2], [5, 5, 8, 8]), 0, "disjoint plots share nothing");
assert.equal(plotOverlap([0, 0, 2, 2], [2, 0, 4, 2]), 0, "an edge touch shares nothing");
assert.equal(plotOverlap([-3, -2, 1, 2], [-1, -1, 4, 1]), 4, "negative edges");
assert.throws(() => plotOverlap([0, 0, 2], [0, 0, 1, 1]), Error, "three entries are rejected");
assert.throws(
  () => plotOverlap([0, 0, 2.5, 2], [0, 0, 1, 1]),
  Error,
  "a fractional edge is rejected",
);
assert.throws(() => plotOverlap([3, 0, 1, 2], [0, 0, 1, 1]), Error, "left at or past right");
console.log("ok");
