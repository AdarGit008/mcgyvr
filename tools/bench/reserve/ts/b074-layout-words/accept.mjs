import assert from "node:assert/strict";
import { layoutWords, lineWidth } from "./solution.ts";

assert.deepEqual(layoutWords([], 10), [], "no words lay out as no lines");
assert.deepEqual(layoutWords(["ab"], 5), [["ab"]], "one word, one line");
assert.deepEqual(
  layoutWords(["ab", "cd", "ef"], 7),
  [["ab", "cd"], ["ef"]],
  "the joining space counts against the width",
);
assert.deepEqual(
  layoutWords(["aa", "bb"], 4),
  [["aa"], ["bb"]],
  "two words needing a space do not share a width-4 line",
);
assert.deepEqual(
  layoutWords(["abcde", "fg"], 5),
  [["abcde"], ["fg"]],
  "a word exactly the column width stands alone",
);
assert.equal(lineWidth([]), 0, "an empty line has width zero");
assert.equal(lineWidth(["ab", "c"]), 4, "helper counts the joining space");
assert.throws(() => layoutWords(["ab"], 0), Error, "zero width is rejected");
assert.throws(() => layoutWords(["ab"], 6.5), Error, "fractional width");
assert.throws(() => layoutWords([""], 5), Error, "empty word is rejected");
assert.throws(() => layoutWords(["wardrobe"], 5), Error, "word wider than column");
console.log("ok");
