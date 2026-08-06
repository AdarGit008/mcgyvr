import assert from "node:assert/strict";
import { searchRange } from "./solution.ts";

assert.deepEqual(searchRange([], 1), [-1, -1], "empty array");
assert.deepEqual(searchRange([5], 5), [0, 0], "single element hit");
assert.deepEqual(searchRange([5], 4), [-1, -1], "single element miss");
assert.deepEqual(searchRange([5, 7, 7, 8, 8, 10], 8), [3, 4], "interior run");
assert.deepEqual(searchRange([5, 7, 7, 8, 8, 10], 6), [-1, -1], "absent between values");
assert.deepEqual(searchRange([2, 2, 2, 2], 2), [0, 3], "whole array is the run");
assert.deepEqual(searchRange([1, 2, 3], 1), [0, 0], "run at the left edge");
assert.deepEqual(searchRange([1, 2, 3, 3], 3), [2, 3], "run at the right edge");
assert.deepEqual(searchRange([1, 2, 3], 0), [-1, -1], "target below all values");
assert.deepEqual(searchRange([1, 2, 3], 9), [-1, -1], "target above all values");
assert.deepEqual(searchRange([-3, -3, -1, 0], -3), [0, 1], "negative values");
assert.deepEqual(searchRange([0.5, 1.5, 1.5], 1.5), [1, 2], "non-integer values");

// O(log n) requirement: a Proxy counts element reads; 2^20 elements must need
// few comparisons. A linear scan would read hundreds of thousands of elements.
const big = new Array(1 << 20);
for (let i = 0; i < big.length; i++) big[i] = i >> 4; // runs of 16 equal values
let reads = 0;
const counted = new Proxy(big, {
  get(arr, prop) {
    if (typeof prop === "string" && /^\d+$/.test(prop)) reads += 1;
    return Reflect.get(arr, prop);
  },
});
assert.deepEqual(searchRange(counted, 1000), [16000, 16015], "large array run");
assert.ok(reads <= 200, `binary search required: ${reads} element reads is too many`);

const frozen = Object.freeze([1, 2, 2, 3]);
assert.deepEqual(searchRange(frozen, 2), [1, 2], "must not mutate (frozen input)");
