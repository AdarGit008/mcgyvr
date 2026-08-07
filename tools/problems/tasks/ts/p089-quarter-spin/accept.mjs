import assert from "node:assert/strict";
import { quarterSpin } from "./solution.ts";

const tile = [[1, 2, 3], [4, 5, 6]];
assert.deepEqual(quarterSpin(tile, 1), [[4, 1], [5, 2], [6, 3]], "one turn of a 2x3 grid");
assert.deepEqual(tile, [[1, 2, 3], [4, 5, 6]], "the argument grid is untouched");
assert.deepEqual(quarterSpin(tile, 2), [[6, 5, 4], [3, 2, 1]], "two turns of a 2x3 grid");
assert.deepEqual(quarterSpin(tile, 3), [[3, 6], [2, 5], [1, 4]], "three turns of a 2x3 grid");
assert.deepEqual(quarterSpin(tile, 0), [[1, 2, 3], [4, 5, 6]], "zero turns is a plain copy");
assert.deepEqual(quarterSpin(tile, 4), [[1, 2, 3], [4, 5, 6]], "four turns come full circle");
assert.deepEqual(quarterSpin(tile, 7), [[3, 6], [2, 5], [1, 4]], "seven turns act like three");
assert.deepEqual(quarterSpin([[1, 2], [3, 4]], 1), [[3, 1], [4, 2]], "square grids still work");
assert.deepEqual(quarterSpin([[9]], 5), [[9]], "a single cell is unmoved");
console.log("ok");
