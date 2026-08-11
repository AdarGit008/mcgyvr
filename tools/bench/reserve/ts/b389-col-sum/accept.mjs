import assert from "node:assert/strict";
import { colSum } from "./solution.ts";

assert.equal(colSum([[1, 2], [3, 4]], 0), 4, "the first column");
assert.equal(colSum([[1, 2], [3, 4]], 1), 6, "the second column");
assert.equal(colSum([[1], [2, 3]], 1), 3, "a short row adds nothing");
assert.equal(colSum([], 0), 0, "no rows at all");
assert.equal(colSum([[]], 0), 0, "a row holding nothing");
assert.equal(colSum([[5]], 0), 5, "one cell");
console.log("ok");
