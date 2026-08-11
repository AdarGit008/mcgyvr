import assert from "node:assert/strict";
import { bucketCount } from "./solution.ts";

assert.deepEqual(bucketCount([1, 2, 11], 10), { 0: 2, 10: 1 }, "two buckets");
assert.deepEqual(bucketCount([0], 10), { 0: 1 }, "the lowest bucket");
assert.deepEqual(bucketCount([], 10), {}, "no readings at all");
assert.deepEqual(bucketCount([10, 19], 10), { 10: 2 }, "one bucket holds both");
assert.deepEqual(bucketCount([5], 5), { 5: 1 }, "a reading on a boundary goes up");
assert.deepEqual(bucketCount([1, 1, 1], 10), { 0: 3 }, "three in one bucket");
console.log("ok");
