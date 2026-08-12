import assert from "node:assert/strict";
import { weaveRounds, widestList } from "./solution.ts";

assert.deepEqual(
  weaveRounds([[1, 2, 3], [4, 5], [6]]),
  [1, 4, 6, 2, 5, 3],
  "three uneven lanes weave round by round",
);
assert.deepEqual(
  weaveRounds([["a"], ["b", "c", "d"]]),
  ["a", "b", "c", "d"],
  "a short first lane drops out of later rounds",
);
assert.deepEqual(weaveRounds([]), [], "no lanes weave into an empty list");
assert.deepEqual(weaveRounds([[], []]), [], "all-empty lanes weave into an empty list");
assert.deepEqual(weaveRounds([[7, 8, 9]]), [7, 8, 9], "a single lane is copied");
assert.equal(widestList([[1], [2, 3], []]), 2, "widestList finds the longest lane");
assert.equal(widestList([]), 0, "widestList of no lanes is zero");
assert.throws(() => weaveRounds("lanes"), Error, "non-list argument is rejected");
assert.throws(() => weaveRounds([[1], "x"]), Error, "a non-list lane is rejected");
console.log("ok");
