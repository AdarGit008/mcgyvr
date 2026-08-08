import assert from "node:assert/strict";
import { wrapText } from "./solution.ts";

assert.deepEqual(
  wrapText("the quick brown fox jumps", 10),
  ["the quick", "brown fox", "jumps"],
  "greedy fill",
);
assert.deepEqual(wrapText("a bb ccc", 3), ["a", "bb", "ccc"], "narrow lines");
assert.deepEqual(wrapText("one", 80), ["one"], "single word fits");
assert.deepEqual(
  wrapText("hi extraordinary yo", 5),
  ["hi", "extraordinary", "yo"],
  "oversized word gets its own line",
);
assert.deepEqual(wrapText("ab cd", 5), ["ab cd"], "exact width fits");
assert.deepEqual(wrapText("ab cd", 4), ["ab", "cd"], "one short of fitting splits");
assert.throws(() => wrapText("ok", 0), Error, "zero width is rejected");
assert.throws(() => wrapText("ok", 2.5), Error, "fractional width is rejected");
assert.throws(() => wrapText(" lead", 10), Error, "leading space is rejected");
assert.throws(() => wrapText("trail ", 10), Error, "trailing space is rejected");
assert.throws(() => wrapText("a  b", 10), Error, "doubled space is rejected");
assert.throws(() => wrapText(42, 10), Error, "non-string text is rejected");
console.log("ok");
