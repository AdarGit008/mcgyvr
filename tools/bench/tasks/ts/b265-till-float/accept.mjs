import assert from "node:assert/strict";
import { tillFloat } from "./solution.ts";

assert.deepEqual(tillFloat(30, [20, 10, 5]), [1, 1, 0], "one of each of two coins");
assert.deepEqual(tillFloat(45, [20, 10, 5]), [2, 0, 1], "two of the largest coin");
assert.deepEqual(tillFloat(7, [5, 1]), [1, 2], "two of the smallest coin");
assert.deepEqual(tillFloat(0, [10]), [0], "nothing to hand back");
assert.deepEqual(tillFloat(100, [50]), [2], "the same coin twice over");
assert.deepEqual(tillFloat(3, [5]), [0], "the coin is too big");
console.log("ok");
