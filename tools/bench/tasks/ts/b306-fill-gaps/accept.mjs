import assert from "node:assert/strict";
import { isGap, fillGaps } from "./solution.ts";

assert.equal(isGap(-1), true, "minus one is missing");
assert.equal(isGap(0), false, "zero is a real reading");
assert.deepEqual(fillGaps([5, -1, 7]), [5, 5, 7], "the earlier reading fills it");
assert.deepEqual(fillGaps([-1, 5]), [-1, 5], "nothing came before");
assert.deepEqual(fillGaps([]), [], "no readings at all");
assert.deepEqual(
  fillGaps([-1, 5, -1, 7]),
  [-1, 5, 5, 7],
  "a leading gap stays, a later one fills",
);
assert.deepEqual(fillGaps([3, 3]), [3, 3], "nothing to fill");
console.log("ok");
