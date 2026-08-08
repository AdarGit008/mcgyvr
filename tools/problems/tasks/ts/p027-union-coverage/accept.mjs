import assert from "node:assert/strict";
import { unionCoverage } from "./solution.ts";

assert.equal(unionCoverage([[0, 0, 4, 3]]), 12, "single rectangle");
assert.equal(unionCoverage([[0, 0, 2, 2], [5, 5, 7, 8]]), 10, "disjoint pair sums");
assert.equal(unionCoverage([[0, 0, 2, 2], [0, 0, 2, 2]]), 4, "duplicate counted once");
assert.equal(unionCoverage([[0, 0, 3, 3], [1, 1, 4, 4]]), 14, "partial overlap once");
assert.equal(unionCoverage([[0, 0, 10, 10], [2, 2, 5, 5]]), 100, "containment adds nothing");
assert.equal(unionCoverage([[0, 3, 9, 6], [3, 0, 6, 9]]), 45, "crossing strips");
assert.equal(unionCoverage([[-2, -2, 0, 0], [-1, -1, 1, 1]]), 7, "negative coordinates");
assert.equal(unionCoverage([[0, 0, 1, 1], [1, 0, 2, 1]]), 2, "edge-adjacent, no overlap");
assert.equal(unionCoverage([]), 0, "empty list covers nothing");
assert.throws(() => unionCoverage([[0, 0, 0, 5]]), Error, "zero width is rejected");
assert.throws(() => unionCoverage([[2, 0, 1, 3]]), Error, "reversed corners are rejected");
assert.throws(() => unionCoverage([[0, 0, 1.5, 1]]), Error, "fractional corner is rejected");
assert.throws(() => unionCoverage([[0, 0, 1]]), Error, "three-number entry is rejected");
assert.throws(() => unionCoverage([[0, 0, 20001, 1]]), Error, "out-of-range is rejected");
console.log("ok");
