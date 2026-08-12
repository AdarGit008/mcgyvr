import assert from "node:assert/strict";
import { trimCaption } from "./solution.ts";

assert.equal(trimCaption("on time", 20), "on time", "short text is unchanged");
assert.equal(trimCaption("exact fit", 9), "exact fit", "text at exactly the limit is unchanged");
assert.equal(trimCaption("the quick brown fox", 10), "the quick…", "a cut at a word boundary keeps the word");
assert.equal(trimCaption("the quick brown fox", 12), "the quick…", "a mid-word cut drops back to the last space");
assert.equal(trimCaption("extraordinary", 6), "extra…", "a first word too long is cut short");
assert.equal(trimCaption("ab   cdef", 6), "ab…", "hanging spaces are removed before the ellipsis");
assert.throws(() => trimCaption(42, 5), Error, "non-string text is rejected");
assert.throws(() => trimCaption("hello world", 0), Error, "a zero limit is rejected");
assert.throws(() => trimCaption("hello world", 2.5), Error, "a fractional limit is rejected");
console.log("ok");
