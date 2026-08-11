import assert from "node:assert/strict";
import { blankRow, fillRows } from "./solution.ts";

assert.deepEqual(blankRow(3), [0, 0, 0], "a row of zeros");
assert.deepEqual(blankRow(0), [], "a row of no width");
assert.deepEqual(fillRows(2, 2), [[0, 0], [0, 0]], "two rows");
assert.deepEqual(fillRows(0, 3), [], "no rows at all");

const grid = fillRows(2, 2);
grid[0][0] = 9;
assert.deepEqual(grid[1], [0, 0], "writing into one row leaves the other alone");
assert.throws(() => blankRow(-1), Error, "a negative width is rejected");
console.log("ok");
