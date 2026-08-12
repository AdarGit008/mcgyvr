import assert from "node:assert/strict";
import { pivotMargins } from "./solution.ts";

assert.deepEqual(
  pivotMargins([]),
  {
    rows: [],
    cols: [],
    cells: [],
    rowTotals: [],
    colTotals: [],
    grand: 0,
    blanks: 0,
    leaders: [],
  },
  "no entries yields an empty table",
);
assert.deepEqual(
  pivotMargins([["north", "q1", 5]]),
  {
    rows: ["north"],
    cols: ["q1"],
    cells: [[5]],
    rowTotals: [5],
    colTotals: [5],
    grand: 5,
    blanks: 0,
    leaders: ["q1"],
  },
  "a single entry is a one-cell table",
);
assert.deepEqual(
  pivotMargins([["north", "q1", 2], ["north", "q1", 3]]).cells,
  [[5]],
  "entries on the same cell accumulate",
);
assert.deepEqual(
  pivotMargins([
    ["north", "q1", 1],
    ["north", "q2", 2],
    ["south", "q1", 3],
    ["south", "q2", 4],
  ]),
  {
    rows: ["south", "north"],
    cols: ["q2", "q1"],
    cells: [[4, 3], [2, 1]],
    rowTotals: [7, 3],
    colTotals: [6, 4],
    grand: 10,
    blanks: 0,
    leaders: ["q2", "q2"],
  },
  "rows and cols both come back ordered by descending total",
);
assert.deepEqual(
  pivotMargins([["a", "x", 1], ["b", "y", 2]]),
  {
    rows: ["b", "a"],
    cols: ["y", "x"],
    cells: [[2, 0], [0, 1]],
    rowTotals: [2, 1],
    colTotals: [2, 1],
    grand: 3,
    blanks: 2,
    leaders: ["y", "x"],
  },
  "cells with no entry read zero and count as blanks",
);
assert.deepEqual(
  pivotMargins([["beta", "x", 5], ["alpha", "x", 5]]).rows,
  ["alpha", "beta"],
  "a row total tie is broken alphabetically",
);
assert.deepEqual(
  pivotMargins([["a", "x", 5], ["a", "x", -5], ["a", "y", 3]]),
  {
    rows: ["a"],
    cols: ["y", "x"],
    cells: [[3, 0]],
    rowTotals: [3],
    colTotals: [3, 0],
    grand: 3,
    blanks: 0,
    leaders: ["y"],
  },
  "a cell cancelling to zero is not blank",
);
assert.deepEqual(
  pivotMargins([["r", "zeta", 5], ["r", "alpha", 5]]),
  {
    rows: ["r"],
    cols: ["alpha", "zeta"],
    cells: [[5, 5]],
    rowTotals: [10],
    colTotals: [5, 5],
    grand: 10,
    blanks: 0,
    leaders: ["alpha"],
  },
  "a column tie is alphabetical and a leader tie takes the leftmost",
);
assert.deepEqual(
  pivotMargins([
    ["west", "food", 4],
    ["east", "food", 1],
    ["west", "fuel", 2],
    ["mid", "fuel", 7],
    ["east", "food", 2],
  ]),
  {
    rows: ["mid", "west", "east"],
    cols: ["fuel", "food"],
    cells: [[7, 0], [2, 4], [0, 3]],
    rowTotals: [7, 6, 3],
    colTotals: [9, 7],
    grand: 16,
    blanks: 2,
    leaders: ["fuel", "food", "food"],
  },
  "a three-by-two pivot with holes, ordering and leaders",
);
assert.deepEqual(
  pivotMargins([["low", "x", 1], ["high", "x", 9]]).rows,
  ["high", "low"],
  "the larger row total comes first",
);
assert.deepEqual(
  pivotMargins([["r", "a", 1], ["r", "b", 2], ["r", "c", 3]]),
  {
    rows: ["r"],
    cols: ["c", "b", "a"],
    cells: [[3, 2, 1]],
    rowTotals: [6],
    colTotals: [3, 2, 1],
    grand: 6,
    blanks: 0,
    leaders: ["c"],
  },
  "one row across three columns orders columns by total",
);
assert.deepEqual(
  pivotMargins([["a", "c", 2], ["b", "c", 2]]),
  {
    rows: ["a", "b"],
    cols: ["c"],
    cells: [[2], [2]],
    rowTotals: [2, 2],
    colTotals: [4],
    grand: 4,
    blanks: 0,
    leaders: ["c", "c"],
  },
  "one column across two tied rows",
);
assert.deepEqual(
  pivotMargins([["neg", "x", -4], ["pos", "x", 3]]),
  {
    rows: ["pos", "neg"],
    cols: ["x"],
    cells: [[3], [-4]],
    rowTotals: [3, -4],
    colTotals: [-1],
    grand: -1,
    blanks: 0,
    leaders: ["x", "x"],
  },
  "negative amounts rank below positive ones",
);
assert.throws(() => pivotMargins("x"), Error, "non-list entries is rejected");
assert.throws(
  () => pivotMargins([["a", "b"]]),
  Error,
  "a two-item entry is rejected",
);
assert.throws(
  () => pivotMargins([["", "c", 1]]),
  Error,
  "an empty row label is rejected",
);
assert.throws(
  () => pivotMargins([[7, "c", 1]]),
  Error,
  "a non-string row label is rejected",
);
assert.throws(
  () => pivotMargins([["r", "", 1]]),
  Error,
  "an empty column label is rejected",
);
assert.throws(
  () => pivotMargins([["r", "c", 2.5]]),
  Error,
  "a fractional amount is rejected",
);
assert.throws(
  () => pivotMargins([["r", "c", "5"]]),
  Error,
  "a string amount is rejected",
);
console.log("ok");
