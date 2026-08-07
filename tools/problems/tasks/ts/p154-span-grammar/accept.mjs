import assert from "node:assert/strict";
import { expandSpanGrammar } from "./solution.ts";

assert.deepEqual(
  expandSpanGrammar("img<1..3>.png"),
  ["img1.png", "img2.png", "img3.png"],
  "a span counts through its range",
);
assert.deepEqual(
  expandSpanGrammar("<08..11>"),
  ["08", "09", "10", "11"],
  "padding follows the width of the first endpoint",
);
assert.deepEqual(
  expandSpanGrammar("<9..11>"),
  ["10", "11", "9"],
  "sort is by code point, not numeric",
);
assert.deepEqual(
  expandSpanGrammar("<b|a>-<1..2>"),
  ["a-1", "a-2", "b-1", "b-2"],
  "groups combine as a cartesian product, then sort",
);
assert.deepEqual(
  expandSpanGrammar("~<a~|b~>"),
  ["<a|b>"],
  "tilde makes the grammar characters literal",
);
assert.deepEqual(expandSpanGrammar("<x|x>"), ["x"], "duplicates collapse");
assert.deepEqual(
  expandSpanGrammar("plain"),
  ["plain"],
  "a groupless pattern stands for itself",
);
assert.throws(() => expandSpanGrammar("<a"), Error, "unclosed group is rejected");
assert.throws(() => expandSpanGrammar("a>b"), Error, "stray close is rejected");
assert.throws(
  () => expandSpanGrammar("<a||b>"),
  Error,
  "empty choice is rejected",
);
assert.throws(
  () => expandSpanGrammar("<5..3>"),
  Error,
  "descending span is rejected",
);
assert.throws(
  () => expandSpanGrammar("<1..600>"),
  Error,
  "oversized span is rejected",
);
assert.throws(
  () => expandSpanGrammar("<a|b><1..300>"),
  Error,
  "oversized product is rejected",
);
assert.throws(() => expandSpanGrammar("~x"), Error, "bad escape is rejected");
assert.throws(
  () => expandSpanGrammar("<a.b>"),
  Error,
  "choice with punctuation is rejected",
);
assert.throws(() => expandSpanGrammar(42), Error, "non-string is rejected");
console.log("ok");
