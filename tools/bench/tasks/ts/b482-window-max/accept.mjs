import assert from "node:assert/strict";
import { windowMax } from "./solution.ts";

assert.deepEqual(windowMax([1, 3, 2, 5], 2), [3, 3, 5], "stretches of two");
assert.deepEqual(windowMax([1, 3, 2, 5], 3), [3, 5], "stretches of three");
assert.deepEqual(windowMax([5, 5, 5], 2), [5, 5], "readings that all match");
assert.deepEqual(windowMax([4], 1), [4], "a stretch of one");
assert.deepEqual(windowMax([1, 2], 3), [], "a run shorter than the width");
assert.deepEqual(windowMax([], 2), [], "a run holding nothing");
console.log("ok");
