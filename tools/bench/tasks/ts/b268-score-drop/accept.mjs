import assert from "node:assert/strict";
import { scoreDrop } from "./solution.ts";

assert.equal(scoreDrop([3, 1, 4]), 7, "the lowest drops out");
assert.equal(scoreDrop([5, 5]), 5, "one of a repeated lowest drops");
assert.equal(scoreDrop([2, 2, 2]), 4, "only one copy drops");
assert.equal(scoreDrop([9]), 0, "a single score totals nothing");
assert.equal(scoreDrop([]), 0, "no scores, no total");
assert.equal(scoreDrop([10, 4, 4, 2]), 18, "only the lowest goes");
console.log("ok");
