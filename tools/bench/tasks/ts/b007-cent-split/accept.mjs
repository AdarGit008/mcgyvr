import assert from "node:assert/strict";
import { applyBps, splitEvenly, sumParts } from "./solution.ts";

assert.deepEqual(splitEvenly(100, 4), [25, 25, 25, 25], "an even total splits evenly");
assert.deepEqual(splitEvenly(10, 3), [4, 3, 3], "the extra cent lands on the first part");
assert.deepEqual(splitEvenly(101, 2), [51, 50], "an odd cent goes to the earlier part");
assert.deepEqual(splitEvenly(2, 3), [1, 1, 0], "more parts than cents pads with zeros");
assert.deepEqual(splitEvenly(0, 3), [0, 0, 0], "a zero total is all zeros");
assert.deepEqual(splitEvenly(7, 1), [7], "one part takes the whole total");
assert.equal(sumParts(splitEvenly(999, 7)), 999, "the parts always re-total");
assert.equal(applyBps(10000, 250), 250, "a round basis-point cut is exact");
assert.equal(applyBps(3333, 150), 50, "a half-cent rounds up");
assert.throws(() => splitEvenly(10.5, 2), Error, "fractional total is rejected");
assert.throws(() => splitEvenly(-1, 2), Error, "negative total is rejected");
assert.throws(() => splitEvenly(10, 0), Error, "zero ways is rejected");
console.log("ok");
