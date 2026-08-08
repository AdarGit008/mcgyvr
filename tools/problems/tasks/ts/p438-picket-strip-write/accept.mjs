import assert from "node:assert/strict";
import { writePicketStrip } from "./solution.ts";

assert.deepEqual(
  writePicketStrip("0"),
  { strip: "nnwwnnnwn", width: 12 },
  "zero is the first two bars wide",
);
assert.deepEqual(
  writePicketStrip("9"),
  { strip: "nnnnnwwwn", width: 12 },
  "nine is the last two bars wide",
);
assert.deepEqual(
  writePicketStrip("4"),
  { strip: "nnnwwnnwn", width: 12 },
  "four opens the second block of choices",
);
assert.deepEqual(
  writePicketStrip("07"),
  { strip: "nnwwnnnnnwwnwn", width: 19 },
  "two digits stand between the guards",
);
assert.deepEqual(
  writePicketStrip("555"),
  { strip: "nnnwnwnnwnwnnwnwnwn", width: 26 },
  "a digit repeats its own five bars",
);
assert.deepEqual(
  writePicketStrip("0123456789"),
  {
    strip: "nnwwnnnwnwnnwnnwnwnnnwnwwnnnwnwnnwnnwnnwwnnnwnwnnnwwwn",
    width: 75,
  },
  "every digit in order",
);

const one = writePicketStrip("6");
assert.equal(one.strip.slice(0, 2), "nn", "the head guard is two narrow bars");
assert.equal(one.strip.slice(-2), "wn", "the tail guard is wide then narrow");
assert.equal(one.strip.length, 9, "one digit makes nine bars in all");
assert.equal(
  [...one.strip.slice(2, 7)].filter((bar) => bar === "w").length,
  2,
  "a digit is drawn with exactly two wide bars",
);

assert.throws(() => writePicketStrip(7), Error, "a number is no digit string");
assert.throws(() => writePicketStrip(""), Error, "an empty string is rejected");
assert.throws(() => writePicketStrip("12a"), Error, "a letter is rejected");
assert.throws(() => writePicketStrip("1 2"), Error, "a space is rejected");
assert.throws(() => writePicketStrip("-4"), Error, "a sign is rejected");
console.log("ok");
