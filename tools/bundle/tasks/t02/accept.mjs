import assert from "node:assert/strict";
import { mergeIntervals } from "./solution.ts";

assert.deepEqual(
  mergeIntervals([[1, 3], [2, 6], [8, 10], [15, 18]]),
  [[1, 6], [8, 10], [15, 18]],
  "overlapping pairs merge",
);
assert.deepEqual(mergeIntervals([]), [], "empty input");
assert.deepEqual(mergeIntervals([[1, 4]]), [[1, 4]], "single interval");
assert.deepEqual(mergeIntervals([[1, 4], [4, 5]]), [[1, 5]], "touching intervals merge");
assert.deepEqual(mergeIntervals([[5, 6], [1, 2]]), [[1, 2], [5, 6]], "unsorted input");
assert.deepEqual(mergeIntervals([[1, 10], [2, 3]]), [[1, 10]], "fully contained interval");

// The contract says pure. Both the outer array and the inner arrays are the
// caller's; the reference failure mode is merging in place through an alias.
const input = [[1, 3], [2, 6]];
const snapshot = JSON.stringify(input);
const result = mergeIntervals(input);
assert.equal(JSON.stringify(input), snapshot, "input must not be mutated");
assert.ok(
  result.every((pair) => !input.includes(pair)),
  "returned pairs must not alias the caller's inner arrays",
);

const frozen = [Object.freeze([1, 3]), Object.freeze([2, 6])];
assert.deepEqual(mergeIntervals(frozen), [[1, 6]], "must not write through to frozen inputs");

assert.throws(() => mergeIntervals([[5, 1]]), Error, "start after end throws");
