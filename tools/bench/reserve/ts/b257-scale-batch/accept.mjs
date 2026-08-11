import assert from "node:assert/strict";
import { scaleBatch } from "./solution.ts";

assert.deepEqual(scaleBatch([2, 3], 2), [4, 6], "doubling stays whole");
assert.deepEqual(scaleBatch([1, 2], 1.5), [2, 3], "a half rounds up");
assert.deepEqual(scaleBatch([4], 0), [0], "scaling to nothing");
assert.deepEqual(scaleBatch([], 2), [], "no ingredients");
assert.deepEqual(scaleBatch([3], 1), [3], "an unchanged batch");
assert.throws(() => scaleBatch([1], -1), Error, "a negative factor is rejected");
console.log("ok");
