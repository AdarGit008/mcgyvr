import assert from "node:assert/strict";
import { readSpelledCount } from "./solution.ts";

assert.equal(readSpelledCount("zero"), 0, "the lone word zero");
assert.equal(readSpelledCount("seven"), 7, "a one-to-nine spelling alone");
assert.equal(readSpelledCount("nineteen"), 19, "the top of the small range");
assert.equal(readSpelledCount("sixty"), 60, "a multiple of ten alone");
assert.equal(readSpelledCount("forty-two"), 42, "a hyphenated tail");
assert.equal(readSpelledCount("one hundred"), 100, "a head with no tail");
assert.equal(readSpelledCount("three hundred forty-five"), 345, "head and hyphenated tail");
assert.equal(readSpelledCount("nine hundred ninety-nine"), 999, "the biggest block");
assert.equal(readSpelledCount("six hundred four"), 604, "head and small tail");
assert.equal(readSpelledCount("one thousand"), 1000, "a block and the scale word");
assert.equal(readSpelledCount("two thousand fifteen"), 2015, "a further block after the scale");
assert.equal(readSpelledCount("seven hundred thousand"), 700000, "a head-only high block");
assert.equal(
  readSpelledCount("nine hundred ninety-nine thousand nine hundred ninety-nine"),
  999999,
  "both blocks at their fullest",
);

assert.throws(() => readSpelledCount(""), Error, "an empty phrase is refused");
assert.throws(() => readSpelledCount(" one"), Error, "a leading blank is refused");
assert.throws(() => readSpelledCount("one  two"), Error, "two blanks running are refused");
assert.throws(() => readSpelledCount("eleventy"), Error, "a word outside the vocabulary");
assert.throws(() => readSpelledCount("hundred"), Error, "hundred with nothing ahead of it");
assert.throws(() => readSpelledCount("twelve hundred"), Error, "a head above nine is refused");
assert.throws(() => readSpelledCount("one hundred hundred"), Error, "hundred twice in a block");
assert.throws(() => readSpelledCount("one thousand two thousand"), Error, "thousand twice");
assert.throws(() => readSpelledCount("thousand five"), Error, "thousand with no block ahead");
assert.throws(() => readSpelledCount("zero one"), Error, "zero beside another word");
assert.throws(() => readSpelledCount("one hundred zero"), Error, "zero used as a tail");
assert.throws(() => readSpelledCount("twenty-eleven"), Error, "a hyphenated tail above nine");
assert.throws(() => readSpelledCount("five-two"), Error, "a hyphen with no multiple of ten");
assert.throws(() => readSpelledCount("one hundred twenty one"), Error, "a two-word tail");
assert.throws(() => readSpelledCount(7), Error, "a non-string is refused");
console.log("ok");
