import assert from "node:assert/strict";
import { blendCongruences } from "./solution.ts";

assert.deepEqual(
  blendCongruences([
    [2, 4],
    [4, 6],
  ]),
  [10, 12],
  "spans sharing a factor merge on their least common multiple",
);
assert.deepEqual(
  blendCongruences([
    [2, 3],
    [3, 5],
    [2, 7],
  ]),
  [23, 105],
  "three spans sharing no factor",
);
assert.deepEqual(
  blendCongruences([
    [1, 3],
    [2, 5],
    [3, 7],
    [4, 11],
  ]),
  [367, 1155],
  "four spans merge to one value",
);
assert.deepEqual(
  blendCongruences([
    [3, 4],
    [3, 6],
    [3, 9],
  ]),
  [3, 36],
  "agreeing rests across overlapping spans",
);
assert.deepEqual(
  blendCongruences([
    [1, 2],
    [2, 4],
  ]),
  [],
  "conflicting congruences yield an empty list",
);
assert.deepEqual(
  blendCongruences([
    [0, 6],
    [3, 4],
  ]),
  [],
  "an odd rest against an even one cannot be reconciled",
);
assert.deepEqual(blendCongruences([[7, 10]]), [7, 10], "a lone pair merges to itself");
assert.deepEqual(
  blendCongruences([[-3, 10]]),
  [7, 10],
  "an incoming rest is folded into its own span",
);
assert.deepEqual(
  blendCongruences([[5, 1]]),
  [0, 1],
  "a span of one leaves every unknown, reported as zero",
);
assert.deepEqual(
  blendCongruences([
    [2, 4],
    [2, 4],
  ]),
  [2, 4],
  "the same congruence twice merges to itself",
);

assert.throws(
  () =>
    blendCongruences([
      [1, 999983],
      [2, 999979],
    ]),
  Error,
  "a merged span past the limit is rejected",
);
assert.throws(() => blendCongruences([]), Error, "an empty list of pairs is rejected");
assert.throws(() => blendCongruences("pairs"), Error, "a non-list argument is rejected");
assert.throws(() => blendCongruences([[1, 0]]), Error, "a span of nothing is rejected");
assert.throws(() => blendCongruences([[1, -4]]), Error, "a negative span is rejected");
assert.throws(() => blendCongruences([[1, 1000001]]), Error, "a span past the ceiling is rejected");
assert.throws(() => blendCongruences([[1.5, 4]]), Error, "a fractional rest is rejected");
assert.throws(
  () => blendCongruences([[1000000001, 4]]),
  Error,
  "a rest past the limit is rejected",
);
assert.throws(() => blendCongruences([[1]]), Error, "an entry that is not a pair is rejected");
console.log("ok");
