import assert from "node:assert/strict";
import { mirrorStepRun } from "./solution.ts";

assert.deepEqual(
  mirrorStepRun(1),
  { words: ["0", "1"], flips: [1] },
  "one mark makes a two-word turn",
);

assert.deepEqual(
  mirrorStepRun(2),
  { words: ["00", "01", "11", "10"], flips: [2, 1, 2] },
  "two marks: the second writing comes back in reverse",
);

assert.deepEqual(
  mirrorStepRun(3),
  {
    words: ["000", "001", "011", "010", "110", "111", "101", "100"],
    flips: [3, 2, 3, 1, 3, 2, 3],
  },
  "three marks, with the leading column flipping once at the halfway notch",
);

const four = mirrorStepRun(4);
assert.equal(four.words.length, 16, "four marks make sixteen words");
assert.equal(four.words[0], "0000", "the turn opens with all marks clear");
assert.equal(four.words[15], "1000", "and closes one mark away from the start");
assert.deepEqual(
  four.flips,
  [4, 3, 4, 2, 4, 3, 4, 1, 4, 3, 4, 2, 4, 3, 4],
  "the flip columns fall into the ruler pattern",
);

const five = mirrorStepRun(5);
let sound = five.words.length === 32 && five.flips.length === 31;
sound = sound && new Set(five.words).size === 32;
for (let i = 1; i < five.words.length && sound; i++) {
  const before = five.words[i - 1];
  const after = five.words[i];
  const altered = [];
  for (let column = 0; column < 5; column++) {
    if (before[column] !== after[column]) {
      altered.push(column + 1);
    }
  }
  sound = altered.length === 1 && altered[0] === five.flips[i - 1];
}
assert.ok(sound, "every notch of a five-mark turn alters the named column only");

const twelve = mirrorStepRun(12);
assert.equal(twelve.words.length, 4096, "twelve marks make four thousand words");
assert.equal(new Set(twelve.words).size, 4096, "and no word repeats");
assert.equal(twelve.flips.length, 4095, "one flip fewer than there are words");
assert.equal(twelve.words[0], "0".repeat(12), "opening word of the long turn");
assert.equal(
  twelve.words[4095],
  "1" + "0".repeat(11),
  "closing word of the long turn",
);

assert.throws(() => mirrorStepRun(0), Error, "a width of nothing is rejected");
assert.throws(() => mirrorStepRun(13), Error, "a width past twelve is rejected");
assert.throws(() => mirrorStepRun(2.5), Error, "a fractional width is rejected");
assert.throws(() => mirrorStepRun("3"), Error, "text is not a width");
assert.throws(() => mirrorStepRun(null), Error, "nothing at all is rejected");
console.log("ok");
