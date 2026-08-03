import assert from "node:assert/strict";
import { runLengthEncode } from "./solution.ts";

assert.equal(runLengthEncode("aaabbc"), "a3b2c1", "basic runs");
assert.equal(runLengthEncode(""), "", "empty string");
assert.equal(runLengthEncode("a"), "a1", "single character");
assert.equal(runLengthEncode("abc"), "a1b1c1", "no repeats still carry counts");
assert.equal(runLengthEncode("aabbaa"), "a2b2a2", "a run may recur later");
assert.equal(runLengthEncode("a".repeat(12)), "a12", "run longer than nine");
assert.equal(runLengthEncode("  "), " 2", "whitespace is a character like any other");
assert.throws(() => runLengthEncode(42), Error, "non-string argument throws");
