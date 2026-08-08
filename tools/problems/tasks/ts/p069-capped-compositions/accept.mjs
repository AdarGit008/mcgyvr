import assert from "node:assert/strict";
import { cappedCompositions } from "./solution.ts";

assert.equal(cappedCompositions(7, 2, 1, 6), 6, "two dice reach seven six ways");
assert.equal(cappedCompositions(10, 3, 1, 6), 27, "three parts, order counted");
assert.equal(cappedCompositions(6, 4, 0, 3), 44, "zeros allowed as parts");
assert.equal(cappedCompositions(36, 8, 0, 9), 4816030, "eight digits summing to 36");
assert.equal(cappedCompositions(5, 1, 1, 6), 1, "one part in range fits one way");
assert.equal(cappedCompositions(9, 1, 1, 6), 0, "one part cannot exceed hi");
assert.equal(cappedCompositions(3, 2, 4, 6), 0, "total below the floor fits nothing");
assert.equal(cappedCompositions(0, 3, 0, 2), 1, "all-zero sequence is the only fit");
assert.throws(() => cappedCompositions(5, 0, 0, 3), Error, "zero parts rejected");
assert.throws(() => cappedCompositions(5, 2, -1, 3), Error, "negative bound rejected");
assert.throws(() => cappedCompositions(5, 2, 3, 2), Error, "lo above hi rejected");
assert.throws(() => cappedCompositions(1.5, 2, 0, 3), Error, "fractional total rejected");
assert.throws(() => cappedCompositions(5, 2, 0, "6"), Error, "string bound rejected");
console.log("ok");
