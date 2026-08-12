import assert from "node:assert/strict";
import { stampCover, stampTable } from "./solution.ts";

assert.equal(stampCover("abab", [["ab", 3], ["a", 2], ["b", 2]]), 6, "repeating dies");
assert.equal(
  stampCover("abc", [["ab", 5], ["c", 2], ["abc", 9], ["a", 1], ["bc", 3]]),
  4,
  "the cheapest split beats the one-die press",
);
assert.equal(
  stampCover("panel", [["pan", 6], ["el", 2], ["panel", 7]]),
  7,
  "one die may cover the whole label",
);
assert.equal(
  stampCover("aaaa", [["aaa", 1], ["aa", 2], ["a", 5]]),
  4,
  "the longest die first is not always cheapest",
);
assert.deepEqual(
  stampTable([["ab", 3], ["c", 1]]),
  new Map([["ab", 3], ["c", 1]]),
  "the helper builds the price lookup",
);
assert.throws(() => stampCover(42, [["a", 1]]), Error, "non-string label is rejected");
assert.throws(() => stampCover("", [["a", 1]]), Error, "empty label is rejected");
assert.throws(() => stampCover("xy", [["x", 1]]), Error, "an unspellable label is rejected");
assert.throws(() => stampCover("x", [["x", 1], ["x", 2]]), Error, "a die listed twice is rejected");
assert.throws(() => stampCover("x", [["", 1]]), Error, "an empty fragment is rejected");
assert.throws(() => stampCover("x", [["x", 0]]), Error, "a zero price is rejected");
assert.throws(() => stampCover("x", [["x", 1.5]]), Error, "a fractional price is rejected");
console.log("ok");
