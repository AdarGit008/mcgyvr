import assert from "node:assert/strict";
import { foldEnds } from "./solution.ts";

assert.deepEqual(foldEnds([1, 2, 3, 4]), [5, 5], "two pairs folded");
assert.deepEqual(foldEnds([1, 2, 3]), [4, 2], "the middle stands alone");
assert.deepEqual(foldEnds([]), [], "nothing to fold");
assert.deepEqual(foldEnds([7]), [7], "one entry is its own total");
assert.deepEqual(foldEnds([1, 9]), [10], "one pair");
assert.deepEqual(foldEnds([1, 2, 3, 4, 5]), [6, 6, 3], "five entries");
console.log("ok");
