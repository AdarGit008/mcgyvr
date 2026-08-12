import assert from "node:assert/strict";
import { regionTotals } from "./solution.ts";

const grid = [
  [1, 2, 3],
  [4, 5, 6],
  [7, 8, 9],
];

assert.deepEqual(regionTotals([[5]], [[0, 0, 1, 1]]), [5], "single cell grid");
assert.deepEqual(regionTotals(grid, [[0, 0, 3, 3]]), [45], "the whole grid");
assert.deepEqual(regionTotals(grid, [[0, 0, 1, 3]]), [6], "the top row");
assert.deepEqual(regionTotals(grid, [[1, 1, 3, 3]]), [28], "an interior block");
assert.deepEqual(
  regionTotals(grid, [[2, 2, 3, 3]]),
  [9],
  "the bottom-right corner cell",
);
assert.deepEqual(
  regionTotals(grid, [[0, 0, 3, 1], [0, 2, 3, 3], [1, 1, 2, 2]]),
  [12, 18, 5],
  "several queries answer in order",
);
assert.deepEqual(regionTotals(grid, []), [], "no queries, no totals");
assert.deepEqual(
  regionTotals([[-2, 3], [4, -5]], [[0, 0, 2, 2]]),
  [0],
  "negative cells sum",
);
assert.throws(
  () => regionTotals([[1, 2], [3]], [[0, 0, 1, 1]]),
  Error,
  "ragged rows are rejected",
);
assert.throws(() => regionTotals([], []), Error, "an empty grid is rejected");
assert.throws(
  () => regionTotals([[1, 2.5]], [[0, 0, 1, 1]]),
  Error,
  "a fractional cell is rejected",
);
assert.throws(
  () => regionTotals(grid, [[0, 0, 1]]),
  Error,
  "a three-bound query is rejected",
);
assert.throws(
  () => regionTotals(grid, [[1, 0, 1, 3]]),
  Error,
  "an empty block is rejected",
);
assert.throws(
  () => regionTotals(grid, [[0, 0, 4, 3]]),
  Error,
  "a query past the last row is rejected",
);
console.log("ok");
