import assert from "node:assert/strict";
import { placardLines } from "./solution.ts";

assert.deepEqual(placardLines("hello", 10), ["hello"], "one word, one line");
assert.deepEqual(placardLines("ab cd", 5), ["ab cd"], "an exact fit fills the line");
assert.deepEqual(
  placardLines("ab cd ef", 7),
  ["ab cd", "ef"],
  "the joining space counts against the width",
);
assert.deepEqual(
  placardLines("the raven flew over the keep", 10),
  ["the raven", "flew over", "the keep"],
  "greedy fill packs each line",
);
assert.deepEqual(
  placardLines("abcd ef", 4),
  ["abcd", "ef"],
  "a full-width word stands alone",
);
assert.deepEqual(
  placardLines("one two six", 3),
  ["one", "two", "six"],
  "narrow placard holds one word per line",
);
assert.throws(() => placardLines(42, 10), Error, "non-string text is rejected");
assert.throws(() => placardLines("", 10), Error, "empty text is rejected");
assert.throws(() => placardLines("hi there", 0), Error, "zero width is rejected");
assert.throws(() => placardLines("a  b", 10), Error, "doubled space is rejected");
assert.throws(() => placardLines(" a", 10), Error, "leading space is rejected");
assert.throws(() => placardLines("abcd", 3), Error, "a word wider than the placard is rejected");
console.log("ok");
