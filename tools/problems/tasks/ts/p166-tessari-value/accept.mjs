import assert from "node:assert/strict";
import { tessariValue } from "./solution.ts";

assert.equal(tessariValue("K"), 0, "the lone K is nothing");
assert.equal(tessariValue("L"), 1, "one");
assert.equal(tessariValue("N"), 3, "three");
assert.equal(tessariValue("T"), 8, "eight");
assert.equal(tessariValue("LK"), 9, "nine");
assert.equal(tessariValue("LL"), 10, "ten");
assert.equal(tessariValue("MN"), 21, "twenty-one");
assert.equal(tessariValue("TT"), 80, "the largest pair");
assert.equal(tessariValue("LKK"), 81, "eighty-one");
assert.equal(tessariValue("TQL"), 694, "three glyphs");
assert.equal(tessariValue("RSTP"), 5017, "four glyphs");

assert.throws(() => tessariValue(""), Error, "empty text rejected");
assert.throws(() => tessariValue("A"), Error, "foreign glyph rejected");
assert.throws(() => tessariValue("lm"), Error, "lower case rejected");
assert.throws(() => tessariValue("KL"), Error, "leading K rejected");
assert.throws(() => tessariValue("KK"), Error, "doubled K rejected");
assert.throws(() => tessariValue("L M"), Error, "space rejected");
assert.throws(() => tessariValue(42), Error, "non-text rejected");
console.log("ok");
