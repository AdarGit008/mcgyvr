import assert from "node:assert/strict";
import { clashPairs } from "./solution.ts";

assert.deepEqual(clashPairs([]), [], "no bookings means no clashes");
assert.deepEqual(clashPairs([[1, 3], [3, 5]]), [], "touching bookings do not clash");
assert.deepEqual(clashPairs([[1, 4], [2, 6]]), [[0, 1]], "overlapping bookings clash");
assert.deepEqual(clashPairs([[0, 10], [2, 4]]), [[0, 1]], "a contained booking clashes");
assert.deepEqual(
  clashPairs([[1, 9], [2, 5], [6, 8]]),
  [[0, 1], [0, 2]],
  "clashes come ordered by first position then second",
);
assert.throws(() => clashPairs("busy"), Error, "a non-list argument is rejected");
assert.throws(() => clashPairs([[1, 2, 3]]), Error, "a three-item booking is rejected");
assert.throws(() => clashPairs([[1, 2.5]]), Error, "a fractional bound is rejected");
assert.throws(() => clashPairs([[5, 5]]), Error, "a booking of no length is rejected");
console.log("ok");
