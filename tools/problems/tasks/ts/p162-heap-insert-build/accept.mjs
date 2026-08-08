import assert from "node:assert/strict";
import { buildMinHeapByInsertion } from "./solution.ts";

assert.deepEqual(buildMinHeapByInsertion([]), [], "empty supply");
assert.deepEqual(buildMinHeapByInsertion([7]), [7], "single value");
assert.deepEqual(buildMinHeapByInsertion([5, 3, 8, 1]), [1, 3, 8, 5], "two lifts");
assert.deepEqual(
  buildMinHeapByInsertion([9, 7, 5, 3, 1]),
  [1, 3, 7, 9, 5],
  "descending supply",
);
assert.deepEqual(buildMinHeapByInsertion([1, 2, 3]), [1, 2, 3], "no trade needed");
assert.deepEqual(buildMinHeapByInsertion([4, 4, 4]), [4, 4, 4], "equal never trades");
assert.deepEqual(buildMinHeapByInsertion([-2, -9]), [-9, -2], "negatives");
assert.deepEqual(
  buildMinHeapByInsertion([6, 2, 9, 0, 4, 8]),
  [0, 2, 8, 6, 4, 9],
  "six values",
);
assert.deepEqual(buildMinHeapByInsertion([0, 0, 1, 0]), [0, 0, 1, 0], "zeros hold");
assert.throws(() => buildMinHeapByInsertion("abc"), Error, "string is not a list");
assert.throws(() => buildMinHeapByInsertion(null), Error, "null is not a list");
assert.throws(() => buildMinHeapByInsertion([1, 2.5]), Error, "fraction rejected");
assert.throws(() => buildMinHeapByInsertion([1, "3"]), Error, "text entry rejected");
assert.throws(() => buildMinHeapByInsertion([1, true]), Error, "boolean rejected");
assert.throws(() => buildMinHeapByInsertion([NaN]), Error, "NaN rejected");
console.log("ok");
