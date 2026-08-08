import assert from "node:assert/strict";
import { findLineOfFour } from "./solution.ts";

assert.deepEqual(
  findLineOfFour(["....", "....", "....", "rrrr"]),
  {
    winner: "r",
    cells: [
      [3, 0],
      [3, 1],
      [3, 2],
      [3, 3],
    ],
  },
  "four along the floor",
);
assert.deepEqual(
  findLineOfFour(["y...", "y...", "y...", "y..."]),
  {
    winner: "y",
    cells: [
      [0, 0],
      [1, 0],
      [2, 0],
      [3, 0],
    ],
  },
  "four stacked in one column",
);
assert.deepEqual(
  findLineOfFour(["r...", "yr..", "yyr.", "yyyr"]),
  {
    winner: "r",
    cells: [
      [0, 0],
      [1, 1],
      [2, 2],
      [3, 3],
    ],
  },
  "four running down and right",
);
assert.deepEqual(
  findLineOfFour(["...y", "..yr", ".yrr", "yrrr"]),
  {
    winner: "y",
    cells: [
      [3, 0],
      [2, 1],
      [1, 2],
      [0, 3],
    ],
  },
  "four running up and right",
);
assert.deepEqual(
  findLineOfFour(["....", "....", "....", "ryry"]),
  { winner: "none", cells: [] },
  "a floor of alternating marks wins nothing",
);
assert.deepEqual(
  findLineOfFour(["....", "....", "....", "...."]),
  { winner: "none", cells: [] },
  "a vacant board wins nothing",
);
assert.deepEqual(
  findLineOfFour(["..", ".."]),
  { winner: "none", cells: [] },
  "a board too small to hold four",
);
assert.deepEqual(
  findLineOfFour(["....", "....", "rrrr", "yyyy"]),
  {
    winner: "r",
    cells: [
      [2, 0],
      [2, 1],
      [2, 2],
      [2, 3],
    ],
  },
  "the higher line is met first in the sweep",
);
assert.deepEqual(
  findLineOfFour(["rrrr", "ryyy", "ryyy", "ryyy"]),
  {
    winner: "r",
    cells: [
      [0, 0],
      [0, 1],
      [0, 2],
      [0, 3],
    ],
  },
  "right is tried before down",
);
assert.throws(
  () => findLineOfFour("rrrr"),
  Error,
  "a board that is not a list is thrown out",
);
assert.throws(
  () => findLineOfFour([]),
  Error,
  "a board with no lines is thrown out",
);
assert.throws(
  () => findLineOfFour([["r"]]),
  Error,
  "a line that is not a string is thrown out",
);
assert.throws(
  () => findLineOfFour(["rr", ""]),
  Error,
  "an empty line is thrown out",
);
assert.throws(
  () => findLineOfFour(["rr", "rrr"]),
  Error,
  "lines of unequal length are thrown out",
);
assert.throws(
  () => findLineOfFour(["rb.."]),
  Error,
  "a mark outside r, y and the dot is thrown out",
);
assert.throws(
  () => findLineOfFour(["r...", "...."]),
  Error,
  "a hanging disc is thrown out",
);
assert.throws(
  () => findLineOfFour(["r.", ".r"]),
  Error,
  "a disc over a vacant square is thrown out",
);
console.log("ok");
