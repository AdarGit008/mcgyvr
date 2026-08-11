import assert from "node:assert/strict";
import { columnDigest } from "./solution.ts";

assert.deepEqual(columnDigest([[1, 5, 9], [2, 7], [3, 6, 4], [4]], 1), { count: 3, min: 5, max: 7, mean: 6, median: 6 }, "rows too short for the column are passed over");
assert.deepEqual(columnDigest([[1], [2], [4], [7]], 0), { count: 4, min: 1, max: 7, mean: 3.5, median: 3 }, "an even count averages the two middle cells");
assert.deepEqual(columnDigest([[1], [2], [2]], 0), { count: 3, min: 1, max: 2, mean: 1.67, median: 2 }, "a repeating average is cut to two decimals");
assert.deepEqual(columnDigest([[0], [0], [0], [0.5]], 0), { count: 4, min: 0, max: 0.5, mean: 0.13, median: 0 }, "a value halfway at the third decimal rounds upward");
assert.deepEqual(columnDigest([[-4], [-1], [2]], 0), { count: 3, min: -4, max: 2, mean: -1, median: -1 }, "negative cells sort below positive ones");
assert.deepEqual(columnDigest([[1], [2]], 3), { count: 0, min: 0, max: 0, mean: 0, median: 0 }, "a column no row reaches digests as zeros");
console.log("ok");
