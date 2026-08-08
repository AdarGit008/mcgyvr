import assert from "node:assert/strict";
import { mirrorStepRank } from "./solution.ts";

assert.equal(mirrorStepRank("0"), 0, "one mark, first position");
assert.equal(mirrorStepRank("1"), 1, "one mark, second position");

assert.deepEqual(
  ["00", "01", "11", "10"].map(mirrorStepRank),
  [0, 1, 2, 3],
  "the two-mark engraving runs straight up",
);

assert.deepEqual(
  ["000", "001", "011", "010", "110", "111", "101", "100"].map(mirrorStepRank),
  [0, 1, 2, 3, 4, 5, 6, 7],
  "the three-mark engraving runs straight up",
);

assert.equal(mirrorStepRank("0000"), 0, "four marks all clear");
assert.equal(mirrorStepRank("1000"), 15, "the far end of the four-mark dial");
assert.equal(mirrorStepRank("1100"), 8, "halfway round the four-mark dial");
assert.equal(mirrorStepRank("0101"), 6, "a four-mark word part way along");
assert.equal(
  mirrorStepRank("00000000"),
  0,
  "eight clear marks still stand at nought",
);
assert.equal(
  mirrorStepRank("11111111"),
  170,
  "eight marks all set, alternating in plain binary",
);
assert.equal(
  mirrorStepRank("1" + "0".repeat(29)),
  1073741823,
  "the longest word allowed, at the far end of its dial",
);

assert.throws(() => mirrorStepRank(""), Error, "an empty word is rejected");
assert.throws(() => mirrorStepRank(101), Error, "a number is not a word");
assert.throws(() => mirrorStepRank("012"), Error, "a stray mark is rejected");
assert.throws(() => mirrorStepRank("10 1"), Error, "a space is a stray mark");
assert.throws(
  () => mirrorStepRank("0".repeat(31)),
  Error,
  "thirty-one marks is too long",
);
console.log("ok");
