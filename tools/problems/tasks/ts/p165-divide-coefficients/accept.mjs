import assert from "node:assert/strict";
import { divideCoefficients } from "./solution.ts";

assert.deepEqual(
  divideCoefficients([-1, 0, 1], [-1, 1]),
  [[1, 1], []],
  "difference of squares divides cleanly",
);
assert.deepEqual(divideCoefficients([2, 3, 1], [1, 1]), [[2, 1], []], "two roots");
assert.deepEqual(
  divideCoefficients([1, 0, 0, 1], [0, 1]),
  [
    [0, 0, 1],
    [1],
  ],
  "leftover survives",
);
assert.deepEqual(divideCoefficients([4, 8], [2]), [[2, 4], []], "constant divisor");
assert.deepEqual(
  divideCoefficients([6, -5, 1], [-2, 1]),
  [[-3, 1], []],
  "negative coefficients",
);
assert.deepEqual(
  divideCoefficients([1, 0, 4], [1, 2]),
  [
    [-1, 2],
    [2],
  ],
  "quotient turns negative mid-way",
);
assert.deepEqual(
  divideCoefficients([1, 2], [1, 0, 1]),
  [[], [1, 2]],
  "divisor longer than the dividend",
);
assert.deepEqual(divideCoefficients([], [1, 1]), [[], []], "nothing to divide");

assert.throws(
  () => divideCoefficients([0, 0, 1], [1, 2]),
  Error,
  "inexact leading step rejected",
);
assert.throws(
  () => divideCoefficients([0, 1, 1], [0, 3]),
  Error,
  "leading coefficient does not divide",
);
assert.throws(() => divideCoefficients([1, 1], []), Error, "empty divisor rejected");
assert.throws(() => divideCoefficients([1, 0], [1]), Error, "trailing zero rejected");
assert.throws(() => divideCoefficients([1.5], [1]), Error, "fraction rejected");
assert.throws(() => divideCoefficients("t", [1]), Error, "non-list rejected");
console.log("ok");
