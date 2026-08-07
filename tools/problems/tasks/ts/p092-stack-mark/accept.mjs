import assert from "node:assert/strict";
import { canonicalStackMark } from "./solution.ts";

assert.equal(canonicalStackMark("3n17"), "3N017", "joined directly");
assert.equal(canonicalStackMark("3-N-17"), "3N017", "hyphen separators");
assert.equal(canonicalStackMark("3 n 017"), "3N017", "space separators, leading zero");
assert.equal(canonicalStackMark("9w1"), "9W001", "single-digit stack pads to three");
assert.equal(canonicalStackMark("5E999"), "5E999", "already canonical survives");
assert.equal(canonicalStackMark("7s  042"), "7S042", "multiple spaces allowed");
assert.equal(canonicalStackMark("2e-5"), "2E005", "mixed joining styles");
assert.throws(() => canonicalStackMark(""), Error, "empty string is rejected");
assert.throws(() => canonicalStackMark("0n17"), Error, "floor 0 is rejected");
assert.throws(() => canonicalStackMark("3x17"), Error, "unknown wing is rejected");
assert.throws(() => canonicalStackMark("3n000"), Error, "stack value 0 is rejected");
assert.throws(() => canonicalStackMark("3n0017"), Error, "four digits are rejected");
assert.throws(() => canonicalStackMark("3--n17"), Error, "double hyphen is rejected");
assert.throws(() => canonicalStackMark("3n17b"), Error, "trailing junk is rejected");
assert.throws(() => canonicalStackMark(42), Error, "non-string is rejected");
console.log("ok");
