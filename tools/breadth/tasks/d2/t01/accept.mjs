import assert from "node:assert/strict";
import { mergeIntervals } from "./solution.ts";

assert.deepEqual(mergeIntervals([]), [], "empty input");
assert.deepEqual(mergeIntervals([[5, 7]]), [[5, 7]], "single interval");
assert.deepEqual(
  mergeIntervals([[1, 3], [2, 6], [8, 10], [15, 18]]),
  [[1, 6], [8, 10], [15, 18]],
  "classic overlap"
);
assert.deepEqual(mergeIntervals([[1, 2], [2, 3]]), [[1, 3]], "touching intervals merge");
assert.deepEqual(mergeIntervals([[1, 10], [2, 3], [4, 5]]), [[1, 10]], "containment");
assert.deepEqual(
  mergeIntervals([[8, 9], [1, 4], [3, 5], [7, 8]]),
  [[1, 5], [7, 9]],
  "unsorted input"
);
assert.deepEqual(
  mergeIntervals([[-5, -3], [-4, 0], [1, 1]]),
  [[-5, 0], [1, 1]],
  "negatives and a point interval"
);
assert.deepEqual(mergeIntervals([[2, 2], [2, 2]]), [[2, 2]], "duplicate point intervals");

const input = [[3, 4], [1, 2]];
const snapshot = JSON.stringify(input);
mergeIntervals(input);
assert.equal(JSON.stringify(input), snapshot, "input must not be mutated");

assert.throws(() => mergeIntervals([[3, 1]]), Error, "start > end throws");
assert.throws(() => mergeIntervals([[1]]), Error, "non-pair element throws");
assert.throws(() => mergeIntervals([[1, Infinity]]), Error, "non-finite bound throws");
