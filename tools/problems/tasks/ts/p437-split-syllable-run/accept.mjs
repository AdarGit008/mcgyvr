import assert from "node:assert/strict";
import { splitSyllables } from "./solution.ts";

assert.deepEqual(splitSyllables("basket", 1), ["bas", "ket"], "two consonants part");
assert.deepEqual(splitSyllables("mother", 1), ["mo", "ther"], "th never parts");
assert.deepEqual(splitSyllables("lemon", 1), ["le", "mon"], "a lone consonant goes right");
assert.deepEqual(
  splitSyllables("yellow", 1),
  ["yel", "low"],
  "a leading y is a consonant",
);
assert.deepEqual(splitSyllables("happy", 1), ["hap", "py"], "a trailing y is a vowel");
assert.deepEqual(
  splitSyllables("rhythm", 1),
  ["rhythm"],
  "one nucleus leaves the word whole",
);
assert.deepEqual(splitSyllables("sky", 1), ["sky"], "y alone carries the only nucleus");
assert.deepEqual(
  splitSyllables("monster", 1),
  ["mon", "ster"],
  "a run of three keeps its first letter on the left",
);
assert.deepEqual(
  splitSyllables("bathtub", 1),
  ["ba", "thtub"],
  "a run opening with th goes right entire",
);
assert.deepEqual(
  splitSyllables("elephant", 1),
  ["e", "le", "phant"],
  "three nuclei make three syllables",
);
assert.deepEqual(
  splitSyllables("elephant", 2),
  ["ele", "phant"],
  "the leading syllable joins the one after it",
);
assert.deepEqual(
  splitSyllables("banana", 2),
  ["ba", "na", "na"],
  "two letters each is long enough",
);
assert.deepEqual(
  splitSyllables("banana", 3),
  ["banana"],
  "joining cascades until one syllable stands",
);

assert.throws(() => splitSyllables(5, 1), Error, "a non-string word is rejected");
assert.throws(() => splitSyllables("", 1), Error, "an empty word is rejected");
assert.throws(() => splitSyllables("Basket", 1), Error, "a capital letter is rejected");
assert.throws(() => splitSyllables("bas ket", 1), Error, "a space is rejected");
assert.throws(() => splitSyllables("basket", 0), Error, "a minimum below one is rejected");
assert.throws(() => splitSyllables("basket", 2.5), Error, "a fractional minimum is rejected");
console.log("ok");
