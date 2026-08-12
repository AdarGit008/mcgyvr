import assert from "node:assert/strict";
import { fewestStamps } from "./solution.ts";

assert.deepEqual(
  fewestStamps(6, [1, 3, 4]),
  { count: 2, stamps: [3, 3] },
  "greedy would take 4+1+1; two threes win",
);
assert.deepEqual(
  fewestStamps(0, [5]),
  { count: 0, stamps: [] },
  "zero postage needs no stamps",
);
assert.deepEqual(
  fewestStamps(12, [4]),
  { count: 3, stamps: [4, 4, 4] },
  "a single denomination repeats",
);
assert.deepEqual(
  fewestStamps(7, [3, 4]),
  { count: 2, stamps: [4, 3] },
  "stamps come back in non-increasing order",
);
assert.deepEqual(
  fewestStamps(10, [2, 5]),
  { count: 2, stamps: [5, 5] },
  "two fives beat five twos",
);
assert.deepEqual(
  fewestStamps(6, [1, 2, 3, 4, 5]),
  { count: 2, stamps: [5, 1] },
  "ties prefer the largest stamp at each step",
);
assert.deepEqual(
  fewestStamps(6, [4, 3, 1]),
  { count: 2, stamps: [3, 3] },
  "denomination order does not matter",
);
assert.deepEqual(
  fewestStamps(2, [2]),
  { count: 1, stamps: [2] },
  "one stamp can be the whole answer",
);
assert.throws(() => fewestStamps(7, [2, 4]), Error, "odd postage from even stamps");
assert.throws(() => fewestStamps(3, [5]), Error, "postage below the smallest stamp");
assert.throws(() => fewestStamps(2.5, [1]), Error, "fractional postage is rejected");
assert.throws(() => fewestStamps(5, []), Error, "an empty denomination list");
assert.throws(() => fewestStamps(5, [0, 5]), Error, "a zero denomination is rejected");
assert.throws(() => fewestStamps(5, [2, 2]), Error, "a repeated denomination");
console.log("ok");
