import assert from "node:assert/strict";
import { wrapWords } from "./solution.ts";

assert.deepEqual(wrapWords("a bb ccc", 5), ["a bb", "ccc"], "a line fills then breaks");
assert.deepEqual(
  wrapWords("one two three", 3),
  ["one", "two", "three"],
  "a word wider than the width stands alone",
);
assert.deepEqual(wrapWords("verylongword", 4), ["verylongword"], "one long word");
assert.deepEqual(wrapWords("", 5), [], "no sentence, no lines");
assert.deepEqual(wrapWords("a b c d", 3), ["a b", "c d"], "two to a line");
assert.deepEqual(wrapWords("  spaced   out  ", 20), ["spaced out"], "gaps collapse");
console.log("ok");
