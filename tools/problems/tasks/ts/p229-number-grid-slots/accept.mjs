import assert from "node:assert/strict";
import { numberGridSlots } from "./solution.ts";

assert.deepEqual(
  numberGridSlots(["...", ".#.", "..."]),
  [
    { at: 1, row: 0, col: 0, across: 3, down: 3 },
    { at: 2, row: 0, col: 2, across: 0, down: 3 },
    { at: 3, row: 2, col: 0, across: 3, down: 0 },
  ],
  "a square with a block in the middle",
);

assert.deepEqual(
  numberGridSlots(["...#.", ".#...", ".....", "#...."]),
  [
    { at: 1, row: 0, col: 0, across: 3, down: 3 },
    { at: 2, row: 0, col: 2, across: 0, down: 4 },
    { at: 3, row: 0, col: 4, across: 0, down: 4 },
    { at: 4, row: 1, col: 2, across: 3, down: 0 },
    { at: 5, row: 1, col: 3, across: 0, down: 3 },
    { at: 6, row: 2, col: 0, across: 5, down: 0 },
    { at: 7, row: 2, col: 1, across: 0, down: 2 },
    { at: 8, row: 3, col: 1, across: 4, down: 0 },
  ],
  "a ragged grid numbered right through",
);

assert.deepEqual(
  numberGridSlots(["...."]),
  [{ at: 1, row: 0, col: 0, across: 4, down: 0 }],
  "one row holds one across slot and no down slot",
);

assert.deepEqual(
  numberGridSlots([".", ".", "."]),
  [{ at: 1, row: 0, col: 0, across: 0, down: 3 }],
  "one column holds one down slot and no across slot",
);

assert.deepEqual(numberGridSlots(["###"]), [], "a wholly blocked grid numbers nothing");

assert.deepEqual(
  numberGridSlots([".#.", "###", ".#."]),
  [],
  "single open squares are too short to open anything",
);

assert.deepEqual(
  numberGridSlots(["..#.."]),
  [
    { at: 1, row: 0, col: 0, across: 2, down: 0 },
    { at: 2, row: 0, col: 3, across: 2, down: 0 },
  ],
  "a block starts the count again further along the row",
);

assert.deepEqual(
  numberGridSlots(["..", ".."]),
  [
    { at: 1, row: 0, col: 0, across: 2, down: 2 },
    { at: 2, row: 0, col: 1, across: 0, down: 2 },
    { at: 3, row: 1, col: 0, across: 2, down: 0 },
  ],
  "the smallest grid that opens slots both ways",
);

assert.throws(() => numberGridSlots([]), Error, "an empty grid is rejected");
assert.throws(() => numberGridSlots("..."), Error, "rows that are not a list are rejected");
assert.throws(() => numberGridSlots([5]), Error, "a row that is not a string is rejected");
assert.throws(() => numberGridSlots([""]), Error, "an empty row is rejected");
assert.throws(() => numberGridSlots(["..", "..."]), Error, "rows of unlike length are rejected");
assert.throws(() => numberGridSlots(["..x"]), Error, "a character that is neither open nor blocked is rejected");
assert.throws(() => numberGridSlots(["...", " .."]), Error, "a space in the grid is rejected");
console.log("ok");
