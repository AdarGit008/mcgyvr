import assert from "node:assert/strict";
import { runTotal } from "./solution.ts";

assert.deepEqual(runTotal([5, 6, 1, 7], 3), [11, 7], "two runs, the low one excluded");
assert.deepEqual(runTotal([5, 6], 3), [11], "one unbroken run");
assert.deepEqual(runTotal([1, 2], 3), [], "the floor is never reached");
assert.deepEqual(runTotal([], 3), [], "no readings at all");
assert.deepEqual(runTotal([3], 3), [3], "a run of one on the floor");
assert.deepEqual(runTotal([1, 5, 1], 3), [5], "a run between two low readings");
console.log("ok");
