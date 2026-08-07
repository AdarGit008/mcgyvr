import assert from "node:assert/strict";
import { allocateCents } from "./solution.ts";

assert.deepEqual(
  allocateCents(100, [1, 1, 1]),
  [34, 33, 33],
  "the odd cent goes to the earliest party on a remainder tie",
);
assert.deepEqual(
  allocateCents(101, [1, 1, 1]),
  [34, 34, 33],
  "two spare cents reach the two earliest parties",
);
assert.deepEqual(
  allocateCents(100, [1, 1, 3]),
  [20, 20, 60],
  "an exact division needs no correction",
);
assert.deepEqual(
  allocateCents(9, [3, 2, 2]),
  [4, 3, 2],
  "largest remainder first, then earliest on the tie",
);
assert.deepEqual(
  allocateCents(1, [10, 1]),
  [1, 0],
  "a single cent lands on the largest remainder",
);
assert.deepEqual(allocateCents(0, [2, 5]), [0, 0], "nothing splits into nothings");
assert.deepEqual(
  allocateCents(7, [5]),
  [7],
  "one party takes the whole sum",
);
const spread = allocateCents(997, [7, 11, 13]);
assert.equal(spread.reduce((a, b) => a + b, 0), 997, "no cent appears or vanishes");
assert.throws(() => allocateCents(10, []), Error, "empty weights are rejected");
assert.throws(() => allocateCents(10, [1, 0]), Error, "a zero weight is rejected");
assert.throws(() => allocateCents(-5, [1]), Error, "a negative total is rejected");
assert.throws(() => allocateCents(10.5, [1]), Error, "a fractional total is rejected");
assert.throws(() => allocateCents(10, [1.5, 2]), Error, "a fractional weight is rejected");
console.log("ok");
