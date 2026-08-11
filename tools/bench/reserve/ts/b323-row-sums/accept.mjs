import assert from "node:assert/strict";
import { rowSums } from "./solution.ts";

assert.deepEqual(rowSums([[1, 2], [3, 4]]), [3, 7], "a row at a time");
assert.deepEqual(rowSums([[]]), [0], "an empty row totals nothing");
assert.deepEqual(rowSums([]), [], "no rows at all");
assert.deepEqual(rowSums([[5]]), [5], "a row of one");
assert.deepEqual(rowSums([[1, 1, 1], [0]]), [3, 0], "rows of different lengths");
assert.deepEqual(rowSums([[-1, 1]]), [0], "they cancel out");
console.log("ok");
