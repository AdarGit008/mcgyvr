import assert from "node:assert/strict";
import { hyphenateWord } from "./solution.ts";

assert.deepEqual(
  hyphenateWord("ledger", ["d-g", "e-r"], 2),
  ["led", "ger"],
  "one break is taken and the late one would leave a single letter",
);
assert.deepEqual(
  hyphenateWord("ledger", ["d-g", "e-r"], 4),
  ["ledger"],
  "a demanding minimum leaves the word whole",
);
assert.deepEqual(
  hyphenateWord("vacation", ["a-tion"], 2),
  ["vaca", "tion"],
  "a pattern may name several letters on a side",
);
assert.deepEqual(
  hyphenateWord("contrast", ["n-t", "t-r"], 2),
  ["con", "trast"],
  "the second place is passed over: it would close a one-letter piece",
);
assert.deepEqual(
  hyphenateWord("contrast", ["n-t", "t-r"], 1),
  ["con", "t", "rast"],
  "a minimum of one lets both places break",
);
assert.deepEqual(
  hyphenateWord("banana", ["a-n"], 1),
  ["ba", "na", "na"],
  "one pattern may permit several places",
);
assert.deepEqual(
  hyphenateWord("banana", ["a-n"], 3),
  ["banana"],
  "every permitted place would leave too short a tail",
);
assert.deepEqual(hyphenateWord("stone", [], 1), ["stone"], "an empty table breaks nothing");
assert.deepEqual(
  hyphenateWord("stone", ["x-y"], 1),
  ["stone"],
  "a pattern the word never matches breaks nothing",
);
assert.deepEqual(
  hyphenateWord("aa", ["a-a"], 1),
  ["a", "a"],
  "the shortest breakable word breaks once",
);

assert.throws(() => hyphenateWord(12, ["a-b"], 1), Error, "the word must be a string");
assert.throws(() => hyphenateWord("", ["a-b"], 1), Error, "an empty word is rejected");
assert.throws(() => hyphenateWord("Word", ["a-b"], 1), Error, "a capital letter is rejected");
assert.throws(() => hyphenateWord("we ll", ["a-b"], 1), Error, "a space is rejected");
assert.throws(() => hyphenateWord("word", "a-b", 1), Error, "the rules must be a list");
assert.throws(() => hyphenateWord("word", [7], 1), Error, "a non-string pattern is rejected");
assert.throws(() => hyphenateWord("word", ["ab"], 1), Error, "a pattern without a hyphen is rejected");
assert.throws(() => hyphenateWord("word", ["a-b-c"], 1), Error, "two hyphens are rejected");
assert.throws(() => hyphenateWord("word", ["-b"], 1), Error, "an empty left side is rejected");
assert.throws(() => hyphenateWord("word", ["a-"], 1), Error, "an empty right side is rejected");
assert.throws(() => hyphenateWord("word", ["A-b"], 1), Error, "a capital in a pattern is rejected");
assert.throws(() => hyphenateWord("word", ["a-b"], 0), Error, "a minimum below one is rejected");
assert.throws(() => hyphenateWord("word", ["a-b"], 1.5), Error, "a fractional minimum is rejected");
console.log("ok");
