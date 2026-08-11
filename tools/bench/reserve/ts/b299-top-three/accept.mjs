import assert from "node:assert/strict";
import { topThree } from "./solution.ts";

assert.deepEqual(topThree([5, 1, 9, 3]), [9, 5, 3], "the highest three");
assert.deepEqual(topThree([2, 2, 2, 2]), [2, 2, 2], "all the same");
assert.deepEqual(topThree([7, 4]), [7, 4], "fewer than three");
assert.deepEqual(topThree([3]), [3], "one score");
assert.deepEqual(topThree([]), [], "no scores at all");
assert.deepEqual(topThree([1, 2, 3, 4, 5]), [5, 4, 3], "the tail is cut");
console.log("ok");
