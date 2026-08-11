import assert from "node:assert/strict";
import { tideMarks } from "./solution.ts";

assert.deepEqual(tideMarks([1, 3, 2]), [1], "one interior peak");
assert.deepEqual(tideMarks([1, 2, 3]), [], "a rising run has no peak");
assert.deepEqual(tideMarks([3, 2, 1]), [], "a falling run has no peak");
assert.deepEqual(tideMarks([1, 3, 2, 5, 4]), [1, 3], "peaks in increasing order");
assert.deepEqual(tideMarks([2, 2, 2]), [], "a flat run is not a peak");
assert.deepEqual(tideMarks([1, 3, 3, 2]), [], "a plateau is not a peak");
assert.deepEqual(tideMarks([]), [], "no readings, no peaks");
console.log("ok");
