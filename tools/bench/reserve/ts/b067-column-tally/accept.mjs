import assert from "node:assert/strict";
import { tallyColumn } from "./solution.ts";

assert.deepEqual(
  tallyColumn([[1, 5], [2, 7], [3, 6]], 1),
  { count: 3, total: 18, low: 5, high: 7 },
  "middle column of three rows",
);
assert.deepEqual(tallyColumn([[0], [4]], 0), { count: 2, total: 4, low: 0, high: 4 }, "a zero cell still counts");
assert.deepEqual(tallyColumn([[3], [5]], 0), { count: 2, total: 8, low: 3, high: 5 }, "low comes from the data");
assert.deepEqual(tallyColumn([[-2], [-6]], 0), { count: 2, total: -8, low: -6, high: -2 }, "all-negative column");
assert.deepEqual(tallyColumn([[9, 1]], 0), { count: 1, total: 9, low: 9, high: 9 }, "single row");
assert.throws(() => tallyColumn([], 0), Error, "empty table is rejected");
assert.throws(() => tallyColumn([[1, 2], [3]], 0), Error, "ragged rows are rejected");
assert.throws(() => tallyColumn([[1, 2]], 2), Error, "column outside the rows is rejected");
assert.throws(() => tallyColumn([[1], ["7"]], 0), Error, "non-number cell is rejected");
console.log("ok");
