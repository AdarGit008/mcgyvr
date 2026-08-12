import assert from "node:assert/strict";
import { cellAt, diagOf } from "./solution.ts";

assert.equal(cellAt([[1, 2], [3, 4]], 0, 1), 2, "a cell inside the grid");
assert.equal(cellAt([[1]], 5, 0), 0, "a row outside the grid");
assert.deepEqual(diagOf([[1, 2], [3, 4]]), [1, 4], "the main diagonal");
assert.deepEqual(diagOf([]), [], "no rows, no diagonal");
assert.deepEqual(diagOf([[1]]), [1], "a grid of one cell");
assert.deepEqual(diagOf([[1, 2, 3], [4, 5, 6]]), [1, 5], "one step for each row");
console.log("ok");
