import assert from "node:assert/strict";
import { shingleOverlapRatio } from "./solution.ts";

assert.deepEqual(
  shingleOverlapRatio("the quick brown fox", "the quick brown dog", 2),
  [1, 2],
  "pairs of tokens, half shared",
);
assert.deepEqual(
  shingleOverlapRatio("the quick brown fox", "the quick brown dog", 1),
  [3, 5],
  "single tokens",
);
assert.deepEqual(
  shingleOverlapRatio("the quick brown fox", "the quick brown dog", 3),
  [1, 3],
  "triples of tokens",
);
assert.deepEqual(
  shingleOverlapRatio("p q r s", "r s t u", 1),
  [1, 3],
  "two over six reduces",
);
assert.deepEqual(
  shingleOverlapRatio("alpha beta", "alpha beta", 2),
  [1, 1],
  "identical passages",
);
assert.deepEqual(
  shingleOverlapRatio("a b", "c d", 2),
  [0, 1],
  "nothing in common",
);
assert.deepEqual(
  shingleOverlapRatio("a b a b", "a b", 2),
  [1, 2],
  "a repeated window counts once",
);
assert.deepEqual(
  shingleOverlapRatio("  one   two  three ", "one two three", 2),
  [1, 1],
  "runs of spaces collapse",
);
assert.deepEqual(
  shingleOverlapRatio("x y z", "y z x", 3),
  [0, 1],
  "order matters inside a window",
);
assert.throws(
  () => shingleOverlapRatio("a b", "c d", 0),
  Error,
  "width zero is rejected",
);
assert.throws(
  () => shingleOverlapRatio("a b", "c d", 2.5),
  Error,
  "fractional width is rejected",
);
assert.throws(
  () => shingleOverlapRatio("a b", "c d", 3),
  Error,
  "width past the token count is rejected",
);
assert.throws(
  () => shingleOverlapRatio("a b", "   ", 1),
  Error,
  "a tokenless passage is rejected",
);
assert.throws(
  () => shingleOverlapRatio(7, "c d", 1),
  Error,
  "a non-string passage is rejected",
);
console.log("ok");
