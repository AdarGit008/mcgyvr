import assert from "node:assert/strict";
import { shiftFrontCodes } from "./solution.ts";

const LETTERS = "abcdefghijklmnopqrstuvwxyz";

assert.deepEqual(
  shiftFrontCodes("abcd", "dab"),
  [3, 1, 2],
  "the stated dab example",
);
assert.deepEqual(
  shiftFrontCodes(LETTERS, "banana"),
  [1, 1, 13, 1, 1, 1],
  "an alternating message settles into ones",
);
assert.deepEqual(
  shiftFrontCodes(LETTERS, "bananaaa"),
  [1, 1, 13, 1, 1, 1, 0, 0],
  "a repeat of the head reads zero",
);
assert.deepEqual(shiftFrontCodes("abc", ""), [], "an empty message");
assert.deepEqual(
  shiftFrontCodes("abc", "aaa"),
  [0, 0, 0],
  "the head stays the head",
);
assert.deepEqual(
  shiftFrontCodes("abc", "cba"),
  [2, 2, 2],
  "each character walks in from the tail",
);
assert.deepEqual(
  shiftFrontCodes("xyz", "zzx"),
  [2, 0, 1],
  "the row keeps its order behind the head",
);
assert.deepEqual(
  shiftFrontCodes(".-#", "#.-#"),
  [2, 1, 2, 2],
  "the alphabet need not be letters",
);
assert.throws(
  () => shiftFrontCodes(5, "ab"),
  Error,
  "an alphabet that is not a string is thrown out",
);
assert.throws(
  () => shiftFrontCodes("", ""),
  Error,
  "an empty alphabet is thrown out",
);
assert.throws(
  () => shiftFrontCodes("abca", "a"),
  Error,
  "a repeated alphabet character is thrown out",
);
assert.throws(
  () => shiftFrontCodes("abc", ["a"]),
  Error,
  "a message that is not a string is thrown out",
);
assert.throws(
  () => shiftFrontCodes("abc", "ad"),
  Error,
  "a character outside the alphabet is thrown out",
);
console.log("ok");
