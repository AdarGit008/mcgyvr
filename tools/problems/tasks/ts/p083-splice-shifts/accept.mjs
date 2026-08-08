import assert from "node:assert/strict";
import { spliceShifts } from "./solution.ts";

assert.deepEqual(spliceShifts([[2, 10], [1]]), [1, 2, 10], "numeric order, not text order");
assert.deepEqual(spliceShifts([[1], [5], [3]]), [1, 3, 5], "every sheet counts, not just two");
assert.deepEqual(spliceShifts([[1, 2], [2, 3]]), [1, 2, 3], "a badge on two sheets appears once");
assert.deepEqual(spliceShifts([[4, 4, 4]]), [4], "a badge repeated on one sheet appears once");
assert.deepEqual(spliceShifts([[], [7], []]), [7], "empty sheets contribute nothing");
assert.deepEqual(spliceShifts([]), [], "no sheets gives an empty roster");
assert.deepEqual(
  spliceShifts([[1, 3, 5], [2, 3, 8], [0]]),
  [0, 1, 2, 3, 5, 8],
  "three sheets splice into one ordered roster",
);
assert.deepEqual(spliceShifts([[], []]), [], "only empty sheets gives an empty roster");
console.log("ok");
