import assert from "node:assert/strict";
import { warmUp } from "./solution.ts";

assert.deepEqual(warmUp([1, 2, 5, 1], 3), [5, 1], "the warm-up is dropped");
assert.deepEqual(warmUp([5, 1], 3), [5, 1], "there was no warm-up");
assert.deepEqual(warmUp([1, 1], 3), [], "the floor is never reached");
assert.deepEqual(warmUp([], 3), [], "no readings at all");
assert.deepEqual(warmUp([3], 3), [3], "a reading on the floor counts");
assert.deepEqual(warmUp([1, 4, 1, 4], 4), [4, 1, 4], "only the opening is dropped");
console.log("ok");
