import assert from "node:assert/strict";
import { sketchBars } from "./solution.ts";

assert.deepEqual(
  sketchBars([10, 5, 0], 4),
  ["####", "##..", "...."],
  "largest fills the budget, zero draws nothing",
);
assert.deepEqual(
  sketchBars([3, 1], 4),
  ["####", "#..."],
  "1.33 cells rounds down to one",
);
assert.deepEqual(sketchBars([4, 1], 2), ["##", "#."], "a half cell rounds upward");
assert.deepEqual(
  sketchBars([100, 1], 5),
  ["#####", "#...."],
  "a nonzero value never vanishes",
);
assert.deepEqual(sketchBars([0, 0], 3), ["...", "..."], "all zeros are all dots");
assert.deepEqual(sketchBars([2], 1), ["#"], "budget of one");
assert.deepEqual(
  sketchBars([7, 6, 2], 10),
  ["##########", "#########.", "###......."],
  "proportions over a wider budget",
);
assert.throws(() => sketchBars([], 4), Error, "empty value list is rejected");
assert.throws(() => sketchBars([1, 2], 0), Error, "budget below one is rejected");
assert.throws(() => sketchBars([3, -1], 4), Error, "negative value is rejected");
console.log("ok");
