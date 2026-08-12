import assert from "node:assert/strict";
import { overLimit, limitRun } from "./solution.ts";

assert.equal(overLimit(5, 3), true, "five stands above three");
assert.equal(overLimit(3, 3), false, "sitting on the limit is not over it");
assert.deepEqual(limitRun([1, 2, 9, 1], 3), [1, 2], "the run stops at the breach");
assert.deepEqual(limitRun([9], 3), [], "the opening reading is already over");
assert.deepEqual(limitRun([], 3), [], "no readings at all");
assert.deepEqual(limitRun([1, 2], 3), [1, 2], "nothing breaches the limit");
assert.deepEqual(limitRun([3, 3], 3), [3, 3], "readings on the limit are kept");
console.log("ok");
