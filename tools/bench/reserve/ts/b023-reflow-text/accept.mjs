import assert from "node:assert/strict";
import { reflowText } from "./solution.ts";

assert.deepEqual(
  reflowText("the quick brown fox", 10),
  ["the quick", "brown fox"],
  "basic greedy wrap",
);
assert.deepEqual(reflowText("aaaa bbbbb", 10), ["aaaa bbbbb"], "exact-width fit");
assert.deepEqual(reflowText("abcdefghij", 10), ["abcdefghij"], "word at width");
assert.deepEqual(reflowText("a \t b\n c", 10), ["a b c"], "whitespace collapses");
assert.deepEqual(reflowText("  hi there  ", 8), ["hi there"], "edges trimmed");
assert.deepEqual(reflowText("", 5), [], "empty text yields no lines");
assert.deepEqual(reflowText(" \n\t ", 5), [], "all-whitespace text yields none");
assert.deepEqual(reflowText("one\n\ntwo", 10), ["one", "", "two"], "paragraph gap");
assert.deepEqual(
  reflowText("one\n\n\n\ntwo", 10),
  ["one", "", "two"],
  "blank runs make one gap",
);
assert.deepEqual(
  reflowText("abcdefghijklm", 5),
  ["abcde", "fghij", "klm"],
  "long word breaks into pieces",
);
assert.deepEqual(
  reflowText("abcdefg hi", 5),
  ["abcde", "fg hi"],
  "words join the final piece",
);
assert.deepEqual(
  reflowText("abcdefghij x", 5),
  ["abcde", "fghij", "x"],
  "full final piece takes its line",
);
assert.deepEqual(reflowText("ab c", 1), ["a", "b", "c"], "width one splits all");
assert.deepEqual(reflowText("aaa bb", 4), ["aaa", "bb"], "word moves to next line");
assert.throws(() => reflowText(42, 10), Error, "non-string text is rejected");
assert.throws(() => reflowText("hi", 0), Error, "zero width is rejected");
assert.throws(() => reflowText("hi", -3), Error, "negative width is rejected");
assert.throws(() => reflowText("hi", 2.5), Error, "fractional width is rejected");
console.log("ok");
