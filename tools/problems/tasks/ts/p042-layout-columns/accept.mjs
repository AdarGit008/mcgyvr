import assert from "node:assert/strict";
import { layoutColumns } from "./solution.ts";

assert.deepEqual(
  layoutColumns([["a", "bb"], ["ccc", "d"]], "ll"),
  ["a    bb", "ccc  d"],
  "left alignment pads to the widest cell",
);
assert.deepEqual(
  layoutColumns([["a", "bb"], ["ccc", "d"]], "rr"),
  ["  a  bb", "ccc   d"],
  "right alignment pads on the left",
);
assert.deepEqual(
  layoutColumns([["ab"], ["wxyz"]], "c"),
  [" ab", "wxyz"],
  "centering gives the odd space to the right, then trims it",
);
assert.deepEqual(
  layoutColumns([["a"], ["abcde"]], "c"),
  ["  a", "abcde"],
  "even centering splits padding equally",
);
assert.deepEqual(
  layoutColumns([["x", "y"]], "lr"),
  ["x  y"],
  "columns are separated by exactly two spaces",
);
assert.deepEqual(
  layoutColumns([["hi", "a"], ["z", "b"]], "ll"),
  ["hi  a", "z   b"],
  "no trailing whitespace survives on any line",
);
assert.deepEqual(
  layoutColumns([["", "x"], ["yy", "z"]], "rl"),
  ["    x", "yy  z"],
  "an empty cell still occupies its column width",
);
assert.throws(() => layoutColumns([], "l"), Error, "empty table is rejected");
assert.throws(
  () => layoutColumns([["a", "b"], ["c"]], "ll"),
  Error,
  "ragged row is rejected",
);
assert.throws(
  () => layoutColumns([["a"]], "x"),
  Error,
  "unknown alignment character is rejected",
);
assert.throws(
  () => layoutColumns([["a", "b"]], "l"),
  Error,
  "spec shorter than the rows is rejected",
);
assert.throws(
  () => layoutColumns([[42]], "l"),
  Error,
  "non-string cell is rejected",
);
console.log("ok");
