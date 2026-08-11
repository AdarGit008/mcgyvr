import assert from "node:assert/strict";
import { meanWindow } from "./solution.ts";

assert.deepEqual(meanWindow([1, 2, 3], 2), [1, 2], "two windows, rounded down");
assert.deepEqual(meanWindow([2, 4, 6], 3), [4], "one window over everything");
assert.deepEqual(meanWindow([1, 2], 5), [], "the window does not fit");
assert.deepEqual(meanWindow([], 2), [], "no readings at all");
assert.deepEqual(meanWindow([5, 5, 5], 1), [5, 5, 5], "a window of one");
assert.deepEqual(meanWindow([1, 2, 3, 4], 2), [1, 2, 3], "three windows");
console.log("ok");
