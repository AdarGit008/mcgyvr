import assert from "node:assert/strict";
import { cellName, gridCells } from "./solution.ts";

assert.equal(cellName(0, 0), "A1", "the corner cell");
assert.equal(cellName(2, 1), "B3", "column letter then row number");
assert.deepEqual(gridCells(1, 3), ["A1", "B1", "C1"], "one row across");
assert.deepEqual(gridCells(2, 2), ["A1", "B1", "A2", "B2"], "row by row");
assert.deepEqual(gridCells(0, 5), [], "no rows, no cells");
assert.deepEqual(gridCells(3, 1), ["A1", "A2", "A3"], "one column down");
console.log("ok");
