import assert from "node:assert/strict";
import { runLengthDecode } from "./solution.ts";

assert.equal(runLengthDecode(""), "", "empty string");
assert.equal(runLengthDecode("a1"), "a", "count of one");
assert.equal(runLengthDecode("a3b2c1"), "aaabbc", "basic decode");
assert.equal(runLengthDecode("a12"), "a".repeat(12), "two-digit count");
assert.equal(runLengthDecode("z120"), "z".repeat(120), "count with trailing zero digit");
assert.equal(runLengthDecode("x2y10x1"), "xx" + "y".repeat(10) + "x", "character recurs");
assert.equal(runLengthDecode(" 3"), "   ", "space is a decodable character");
assert.equal(runLengthDecode("#2!1"), "##!", "punctuation decodes like letters");

assert.throws(() => runLengthDecode(7), Error, "non-string input throws");
assert.throws(() => runLengthDecode("3a"), Error, "leading digit throws");
assert.throws(() => runLengthDecode("ab2"), Error, "character without count throws");
assert.throws(() => runLengthDecode("a2b"), Error, "trailing character without count throws");
assert.throws(() => runLengthDecode("a0"), Error, "zero count throws");
assert.throws(() => runLengthDecode("a01"), Error, "count with leading zero throws");
