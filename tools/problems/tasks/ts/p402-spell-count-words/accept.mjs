import assert from "node:assert/strict";
import { spellCountWords } from "./solution.ts";

assert.equal(spellCountWords(0), "zero", "zero is its own small word");
assert.equal(spellCountWords(7), "seven", "single figure");
assert.equal(spellCountWords(13), "thirteen", "teens are small words");
assert.equal(spellCountWords(19), "nineteen", "last small word");
assert.equal(spellCountWords(20), "twenty", "round word alone");
assert.equal(spellCountWords(42), "forty-two", "round word hyphenated");
assert.equal(spellCountWords(90), "ninety", "highest round word");
assert.equal(spellCountWords(100), "one hundred", "bare hundred");
assert.equal(spellCountWords(305), "three hundred and five", "hundred with small leftover");
assert.equal(spellCountWords(760), "seven hundred and sixty", "hundred with round leftover");
assert.equal(
  spellCountWords(999),
  "nine hundred and ninety-nine",
  "largest number under a thousand",
);
assert.equal(spellCountWords(1000), "one thousand", "bare thousand");
assert.equal(spellCountWords(1005), "one thousand and five", "small leftover takes the word and");
assert.equal(spellCountWords(1200), "one thousand two hundred", "big leftover takes a plain blank");
assert.equal(
  spellCountWords(21015),
  "twenty-one thousand and fifteen",
  "hyphenated thousands figure",
);
assert.equal(spellCountWords(100000), "one hundred thousand", "hundred thousand exactly");
assert.equal(
  spellCountWords(999999),
  "nine hundred and ninety-nine thousand nine hundred and ninety-nine",
  "the ceiling",
);
assert.throws(() => spellCountWords(-1), Error, "below zero is refused");
assert.throws(() => spellCountWords(1000000), Error, "above the ceiling is refused");
assert.throws(() => spellCountWords(3.5), Error, "a fraction is refused");
assert.throws(() => spellCountWords("12"), Error, "a string is refused");
assert.throws(() => spellCountWords(Number.NaN), Error, "not-a-number is refused");
console.log("ok");
