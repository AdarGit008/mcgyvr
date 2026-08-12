import assert from "node:assert/strict";
import { padSide, padMid } from "./solution.ts";

assert.equal(padSide(3), "   ", "three spaces");
assert.equal(padSide(0), "", "no spaces at all");
assert.equal(padMid("ab", 6), "  ab  ", "shared evenly");
assert.equal(padMid("ab", 5), " ab  ", "the extra space goes right");
assert.equal(padMid("abc", 3), "abc", "the word fills the field");
assert.equal(padMid("abcd", 2), "abcd", "a wide word is left alone");
console.log("ok");
