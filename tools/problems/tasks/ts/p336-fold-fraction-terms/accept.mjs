import assert from "node:assert/strict";
import { foldFractionTerms } from "./solution.ts";

assert.deepEqual(foldFractionTerms(415, 93), [4, 2, 6, 7], "the worked example");
assert.deepEqual(foldFractionTerms(355, 113), [3, 7, 16], "a famous quotient");
assert.deepEqual(foldFractionTerms(3, 2), [1, 2], "a two-entry run");
assert.deepEqual(foldFractionTerms(1, 1), [1], "one folds to a single entry");
assert.deepEqual(foldFractionTerms(0, 5), [0], "nothing folds to a lone zero");
assert.deepEqual(foldFractionTerms(7, 1), [7], "a whole quantity folds to itself");
assert.deepEqual(foldFractionTerms(1, 3), [0, 3], "a leading zero is allowed");
assert.deepEqual(foldFractionTerms(-7, 2), [-4, 2], "flooring runs downward");
assert.deepEqual(
  foldFractionTerms(-1, 3),
  [-1, 1, 2],
  "a small negative quotient leans on the downward floor",
);
assert.deepEqual(
  foldFractionTerms(6, 4),
  [1, 2],
  "a quotient not in lowest terms folds the same as its reduced form",
);
assert.deepEqual(
  foldFractionTerms(1000000000, 999999999),
  [1, 999999999],
  "the size limit folds exactly",
);
assert.deepEqual(
  foldFractionTerms(13, 8),
  [1, 1, 1, 1, 2],
  "neighbouring counting quantities give a run of ones ending in two",
);

assert.throws(() => foldFractionTerms(1, 0), Error, "a denominator of nothing is rejected");
assert.throws(() => foldFractionTerms(1, -3), Error, "a negative denominator is rejected");
assert.throws(() => foldFractionTerms(1.5, 2), Error, "a fractional numerator is rejected");
assert.throws(() => foldFractionTerms(1, 2.5), Error, "a fractional denominator is rejected");
assert.throws(
  () => foldFractionTerms(1000000001, 2),
  Error,
  "a numerator past the limit is rejected",
);
assert.throws(
  () => foldFractionTerms(1, 1000000001),
  Error,
  "a denominator past the limit is rejected",
);
assert.throws(() => foldFractionTerms("415", 93), Error, "a non-numeric argument is rejected");
console.log("ok");
