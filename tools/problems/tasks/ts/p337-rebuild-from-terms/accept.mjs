import assert from "node:assert/strict";
import { rebuildFromTerms } from "./solution.ts";

assert.deepEqual(rebuildFromTerms([4, 2, 6, 7]), [415, 93], "the worked example");
assert.deepEqual(rebuildFromTerms([3, 7, 16]), [355, 113], "a famous quotient");
assert.deepEqual(rebuildFromTerms([1, 2]), [3, 2], "a two-entry run");
assert.deepEqual(rebuildFromTerms([1]), [1, 1], "a lone one");
assert.deepEqual(rebuildFromTerms([0]), [0, 1], "a lone zero keeps a denominator of one");
assert.deepEqual(rebuildFromTerms([7]), [7, 1], "a lone whole quantity");
assert.deepEqual(rebuildFromTerms([0, 3]), [1, 3], "a leading zero gives a small quotient");
assert.deepEqual(rebuildFromTerms([-4, 2]), [-7, 2], "a negative lead carries through");
assert.deepEqual(
  rebuildFromTerms([-1, 1, 2]),
  [-1, 3],
  "the numerator may end up smaller in size than the lead",
);
assert.deepEqual(
  rebuildFromTerms([1, 1, 1, 1, 2]),
  [13, 8],
  "a run of ones builds neighbouring counting quantities",
);
assert.deepEqual(
  rebuildFromTerms([999, 1000, 1000]),
  [999001999, 1000001],
  "a run close to the swelling limit still rebuilds exactly",
);
assert.deepEqual(
  rebuildFromTerms([2, 1, 1, 1, 2]),
  [21, 8],
  "ones in the middle of a run are ordinary entries",
);

assert.throws(() => rebuildFromTerms([]), Error, "an empty run is rejected");
assert.throws(() => rebuildFromTerms("47"), Error, "a run that is not a list is rejected");
assert.throws(() => rebuildFromTerms([1, 2, 1]), Error, "a run ending in one is rejected");
assert.throws(() => rebuildFromTerms([1, 0]), Error, "an entry of nothing behind the lead is rejected");
assert.throws(() => rebuildFromTerms([1, -3]), Error, "a negative entry behind the lead is rejected");
assert.throws(() => rebuildFromTerms([1, 1001]), Error, "an entry above the ceiling is rejected");
assert.throws(() => rebuildFromTerms([1000001]), Error, "a leading entry too large is rejected");
assert.throws(() => rebuildFromTerms([1.5, 2]), Error, "a fractional entry is rejected");
assert.throws(
  () => rebuildFromTerms([1000000, 1000, 1000]),
  Error,
  "a run that swells past the limit is rejected",
);
assert.throws(
  () => rebuildFromTerms(new Array(65).fill(2)),
  Error,
  "a run of more than 64 entries is rejected",
);
console.log("ok");
