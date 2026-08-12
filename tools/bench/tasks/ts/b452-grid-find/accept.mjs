import assert from "node:assert/strict";
import { matchAt, gridFind } from "./solution.ts";

assert.equal(matchAt([[1]], 0, 0, 1), true, "the cell holds it");
assert.equal(matchAt([[1]], 0, 0, 2), false, "the cell holds something else");
assert.deepEqual(gridFind([[1, 2], [3, 4]], 4), [1, 1], "the last cell");
assert.deepEqual(gridFind([[1]], 1), [0, 0], "the only cell");
assert.deepEqual(gridFind([[1, 2], [2, 3]], 2), [0, 1], "the first of two, read by row");
assert.throws(() => gridFind([[1]], 9), Error, "a value not in the grid is rejected");
console.log("ok");
