import assert from "node:assert/strict";
import { greedyUnitParts } from "./solution.ts";

assert.deepEqual(greedyUnitParts(5, 6), [2, 3], "five sixths splits into two pieces");
assert.deepEqual(greedyUnitParts(3, 7), [3, 11, 231], "three sevenths takes three pieces");
assert.deepEqual(greedyUnitParts(1, 2), [2], "a piece that already fits stays whole");
assert.deepEqual(greedyUnitParts(2, 3), [2, 6], "two thirds splits into a half and a sixth");
assert.deepEqual(greedyUnitParts(4, 5), [2, 4, 20], "four fifths takes three pieces");
assert.deepEqual(greedyUnitParts(9, 20), [3, 9, 180], "nine twentieths takes three pieces");
assert.deepEqual(
  greedyUnitParts(1, 10000),
  [10000],
  "the smallest allowed quotient is already one piece",
);
assert.deepEqual(
  greedyUnitParts(4, 6),
  [2, 6],
  "a quotient handed over unreduced splits like its reduced form",
);

const rising = greedyUnitParts(9, 20);
for (let index = 1; index < rising.length; index++) {
  assert.ok(rising[index] > rising[index - 1], "the somethings rise strictly");
}

assert.throws(
  () => greedyUnitParts(5, 121),
  Error,
  "a quotient whose remainder explodes is rejected",
);
assert.throws(() => greedyUnitParts(0, 5), Error, "a top of nothing is rejected");
assert.throws(() => greedyUnitParts(-1, 5), Error, "a negative top is rejected");
assert.throws(() => greedyUnitParts(5, 5), Error, "a quotient of one is rejected");
assert.throws(() => greedyUnitParts(7, 5), Error, "a quotient above one is rejected");
assert.throws(() => greedyUnitParts(1, 10001), Error, "a bottom past the ceiling is rejected");
assert.throws(() => greedyUnitParts(1, 0), Error, "a bottom of nothing is rejected");
assert.throws(() => greedyUnitParts(1.5, 4), Error, "a fractional top is rejected");
assert.throws(() => greedyUnitParts("1", 4), Error, "a non-numeric top is rejected");
console.log("ok");
