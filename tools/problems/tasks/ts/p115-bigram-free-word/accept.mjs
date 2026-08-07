import assert from "node:assert/strict";
import { smallestFreeWord } from "./solution.ts";

assert.equal(smallestFreeWord(3, 2, []), "aaa", "no bans means all a");
assert.equal(smallestFreeWord(3, 2, ["aa"]), "aba", "aa banned forces alternation");
assert.equal(smallestFreeWord(2, 2, ["aa", "ab"]), "ba", "initial a dead-ends");
assert.equal(smallestFreeWord(4, 2, ["aa", "bb"]), "abab", "strict alternation");
assert.equal(
  smallestFreeWord(1, 2, ["aa", "ab", "ba", "bb"]),
  "a",
  "length one ignores pair bans"
);
assert.equal(
  smallestFreeWord(5, 3, ["aa", "ab", "ac"]),
  "bbbba",
  "a can only ever be the final letter"
);
assert.equal(smallestFreeWord(2, 3, ["aa", "ab"]), "ac", "third letter rescues a");
assert.throws(() => smallestFreeWord(2, 1, ["aa"]), Error, "impossible instance");
assert.throws(() => smallestFreeWord(0, 2, []), Error, "zero length");
assert.throws(() => smallestFreeWord(13, 2, []), Error, "length beyond cap");
assert.throws(() => smallestFreeWord(3, 7, []), Error, "alphabet beyond cap");
assert.throws(() => smallestFreeWord(3, 2, ["abc"]), Error, "three-letter ban");
assert.throws(() => smallestFreeWord(3, 2, ["az"]), Error, "ban outside alphabet");
assert.throws(() => smallestFreeWord(3, 2, "aa"), Error, "banned not a list");
console.log("ok");
