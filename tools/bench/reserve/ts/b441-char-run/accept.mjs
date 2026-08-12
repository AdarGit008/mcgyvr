import assert from "node:assert/strict";
import { charRun } from "./solution.ts";

assert.equal(charRun("aabbb"), 3, "the longer run wins");
assert.equal(charRun("abc"), 1, "no character repeats");
assert.equal(charRun(""), 0, "an empty text");
assert.equal(charRun("aaaa"), 4, "one run throughout");
assert.equal(charRun("a"), 1, "a single character");
assert.equal(charRun("aabaa"), 2, "two runs of the same length");
console.log("ok");
