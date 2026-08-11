import assert from "node:assert/strict";
import { sliceEnd, slicePlan } from "./solution.ts";

assert.equal(sliceEnd(0, 3, 10), 3, "a slice well inside the total");
assert.equal(sliceEnd(8, 3, 10), 10, "a slice held back by the total");
assert.deepEqual(slicePlan(6, 3), [[0, 3], [3, 6]], "two even slices");
assert.deepEqual(slicePlan(7, 3), [[0, 3], [3, 6], [6, 7]], "the last slice is short");
assert.deepEqual(slicePlan(0, 3), [], "nothing to cover");
assert.deepEqual(slicePlan(2, 5), [[0, 2]], "one slice covers it all");
console.log("ok");
