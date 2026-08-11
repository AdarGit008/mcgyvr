import assert from "node:assert/strict";
import { digitWord, digitWords } from "./solution.ts";

assert.equal(digitWord(0), "zero", "the lowest digit");
assert.equal(digitWord(9), "nine", "the highest digit");
assert.equal(digitWords("12"), "one two", "two digits named");
assert.equal(digitWords("7"), "seven", "a single digit");
assert.equal(digitWords(""), "", "no digits at all");
assert.equal(digitWords("305"), "three zero five", "a zero in the middle");
console.log("ok");
