import assert from "node:assert/strict";
import { tallyTuplets } from "./solution.ts";

assert.deepEqual(tallyTuplets("1/4 1/4 1/4 1/4", "4/4"), [0], "a measure that lands");
assert.deepEqual(tallyTuplets("1/2 1/4", "4/4"), [-16], "a hungry measure");
assert.deepEqual(tallyTuplets("1/1 1/4", "4/4"), [16], "an overflowing measure");
assert.deepEqual(
  tallyTuplets("3{1/8+1/8+1/8} 1/4 1/2", "4/4"),
  [0],
  "a figure of three squeezes three eighths into one quarter",
);
assert.deepEqual(
  tallyTuplets("5{1/16+1/16+1/16+1/16+1/16} 1/4 1/4 1/4", "4/4"),
  [0],
  "a figure of five",
);
assert.deepEqual(
  tallyTuplets("7{1/16+1/16+1/16+1/16+1/16+1/16+1/16}", "3/8"),
  [0],
  "a figure of seven fills three eighths",
);
assert.deepEqual(tallyTuplets("3/8 1/8", "2/4"), [0], "a numerator above one");
assert.deepEqual(
  tallyTuplets("1/8 1/8 1/8 1/8 1/8 1/8 1/8", "7/8"),
  [0],
  "an odd meter",
);
assert.deepEqual(
  tallyTuplets("1/4 1/4;1/4", "2/4"),
  [0, -16],
  "two measures, one short",
);
assert.deepEqual(
  tallyTuplets("1/4 1/4 1/4 1/4;3{1/4+1/4+1/4};1/2", "4/4"),
  [0, -32, -32],
  "a squeeze of quarters is worth two of them",
);
assert.deepEqual(
  tallyTuplets("2{1/8+1/8}", "1/8"),
  [0],
  "a figure of two halves the pair",
);

assert.throws(() => tallyTuplets("1/4 1/3", "4/4"), Error, "a bad denominator is rejected");
assert.throws(() => tallyTuplets("1/4 2/4/8", "4/4"), Error, "a misshapen entry is rejected");
assert.throws(() => tallyTuplets("1/4 0/4", "4/4"), Error, "a zero numerator is rejected");
assert.throws(() => tallyTuplets("1/4 01/4", "4/4"), Error, "a padded numerator is rejected");
assert.throws(() => tallyTuplets("1{1/8+1/8}", "4/4"), Error, "a figure of one is rejected");
assert.throws(() => tallyTuplets("3{}", "4/4"), Error, "an empty squeeze is rejected");
assert.throws(() => tallyTuplets("3{1/64+1/64}", "4/4"), Error, "a fractional squeeze is rejected");
assert.throws(() => tallyTuplets("3{1/8+1/8", "4/4"), Error, "an unclosed brace is rejected");
assert.throws(() => tallyTuplets("1/4;;1/4", "4/4"), Error, "an empty measure is rejected");
assert.throws(() => tallyTuplets("1/4", "4/3"), Error, "a bad meter is rejected");
assert.throws(() => tallyTuplets("1/4", "0/4"), Error, "a zero meter is rejected");
assert.throws(() => tallyTuplets(5, "4/4"), Error, "a non-string score is rejected");
console.log("ok");
