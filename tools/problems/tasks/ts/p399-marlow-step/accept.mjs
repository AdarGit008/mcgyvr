import assert from "node:assert/strict";
import { marlowStep } from "./solution.ts";

assert.equal(marlowStep("A", 0), "A", "nought shifted by nothing");
assert.equal(marlowStep("A", 1), "B", "nought up to one");
assert.equal(marlowStep("B", -1), "A", "one back down to nought");
assert.equal(marlowStep("A", -1), "BG", "nought down to minus one");
assert.equal(marlowStep("BG", 0), "BG", "minus one recorded back unchanged");
assert.equal(marlowStep("BA", 7), "A", "minus seven lifted to nought");
assert.equal(marlowStep("A", 7), "BGA", "seven needs three columns");
assert.equal(marlowStep("G", 1), "BGA", "six plus one is seven");
assert.equal(marlowStep("G", -6), "A", "six back to nought");
assert.equal(marlowStep("CD", 0), "CD", "minus eleven survives the round trip");
assert.equal(marlowStep("CD", 11), "A", "minus eleven lifted to nought");
assert.equal(marlowStep("GG", 0), "GG", "minus thirty-six survives too");
assert.equal(marlowStep("BAA", 0), "BAA", "forty-nine is one heavy column");
assert.equal(marlowStep("DEF", 100), "FDA", "a hundred and twenty-four plus a hundred");
assert.equal(marlowStep("A", 1000), "BEAFG", "a thousand from nothing");
assert.equal(marlowStep("A", -1000), "DBDB", "minus a thousand from nothing");

assert.throws(() => marlowStep("", 0), Error, "an empty rung-count is rejected");
assert.throws(() => marlowStep("BH", 0), Error, "a capital past G is rejected");
assert.throws(() => marlowStep("bg", 0), Error, "lower case is rejected");
assert.throws(() => marlowStep("AB", 0), Error, "a padding A is rejected");
assert.throws(() => marlowStep(5, 0), Error, "a number is not a rung-count");
assert.throws(
  () => marlowStep("BAAAAAAAAAAA", 0),
  Error,
  "eleven capitals is too long",
);
assert.throws(() => marlowStep("B", 1.5), Error, "a fractional lift is rejected");
assert.throws(() => marlowStep("B", 1001), Error, "an oversized lift is rejected");
console.log("ok");
