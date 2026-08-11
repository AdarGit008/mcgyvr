import assert from "node:assert/strict";
import { blankCells, fillDown } from "./solution.ts";

assert.deepEqual(
  fillDown([["x"], [""], [""]]),
  [["x"], ["x"], ["x"]],
  "a run of blanks all inherit the value above the run",
);
assert.deepEqual(
  fillDown([["a"], [""], ["b"], [""]]),
  [["a"], ["a"], ["b"], ["b"]],
  "a fresh value resets what later blanks inherit",
);
assert.deepEqual(
  fillDown([
    ["a", "1"],
    ["", ""],
    ["c", ""],
  ]),
  [
    ["a", "1"],
    ["a", "1"],
    ["c", "1"],
  ],
  "columns fill independently",
);
assert.deepEqual(fillDown([]), [], "an empty grid stays empty");
const grid = [["k"], [""]];
fillDown(grid);
assert.deepEqual(grid, [["k"], [""]], "the input grid is left unmodified");
assert.equal(blankCells([["", ""], ["a", ""]]), 3, "blankCells counts the blanks");
assert.throws(
  () => fillDown([["a", "b"], ["c"]]),
  Error,
  "ragged rows are rejected",
);
assert.throws(() => fillDown([[""]]), Error, "a top blank with nothing above");
console.log("ok");
