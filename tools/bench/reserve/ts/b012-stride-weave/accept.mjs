import assert from "node:assert/strict";
import { strideTake, strideSkip, strideWeave } from "./solution.ts";

assert.deepEqual(strideWeave([]), [], "no parts weave to an empty list");
assert.deepEqual(strideWeave([[1, 2, 3]]), [1, 2, 3], "one part is itself");
assert.deepEqual(strideWeave([[1, 3], [2, 4]]), [1, 2, 3, 4], "equal parts");
assert.deepEqual(
  strideWeave([[1, 4, 6], [2, 5], [3]]),
  [1, 2, 3, 4, 5, 6],
  "uneven tails are passed over",
);
assert.deepEqual(
  strideWeave([[1, 3], [], [2, 4]]),
  [1, 2, 3, 4],
  "an empty part never contributes",
);
const whole = [10, 11, 12, 13, 14, 15, 16];
assert.deepEqual(
  strideWeave([
    strideTake(whole, 3, 0),
    strideTake(whole, 3, 1),
    strideTake(whole, 3, 2),
  ]),
  whole,
  "weaving the strides rebuilds the list",
);
assert.deepEqual(strideWeave([[7, 9], [7]]), [7, 7, 9], "duplicates keep order");
assert.throws(() => strideWeave(42), Error, "parts must be a list");
assert.throws(() => strideWeave([[1], 5]), Error, "every part must be a list");
assert.deepEqual(
  strideTake([10, 11, 12, 13, 14], 2, 0),
  [10, 12, 14],
  "take offset 0",
);
assert.deepEqual(strideTake([10, 11, 12, 13, 14], 2, 1), [11, 13], "take offset 1");
assert.throws(() => strideTake([1, 2], 0, 0), Error, "zero step is rejected");
assert.deepEqual(
  strideSkip([10, 11, 12, 13, 14], 2, 0),
  [11, 13],
  "skip is the complement",
);
assert.throws(() => strideSkip([1, 2], 2, 2), Error, "offset must sit below step");
console.log("ok");
