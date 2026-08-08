import assert from "node:assert/strict";
import { wordSpanStarts } from "./solution.ts";

assert.deepEqual(
  wordSpanStarts("The cat sat. THE CAT sat again.", "the cat"),
  [0, 13],
  "case-insensitive hits at original offsets",
);
assert.deepEqual(wordSpanStarts("do do do", "do do"), [0, 3], "overlapping hits");
assert.deepEqual(
  wordSpanStarts("please re-run all re-run jobs", "re run"),
  [7, 18],
  "a hyphen splits words the same way a space does",
);
assert.deepEqual(
  wordSpanStarts("concatenate cats", "cat"),
  [],
  "never matches inside a longer word",
);
assert.deepEqual(
  wordSpanStarts("The cat sat. THE CAT sat again.", "sat, again!"),
  [21],
  "punctuation inside the query is only a separator",
);
assert.deepEqual(wordSpanStarts("", "cat"), [], "empty passage has no hits");
assert.deepEqual(
  wordSpanStarts("v2 build v2 ship", "V2"),
  [0, 9],
  "digits belong to words",
);
assert.throws(() => wordSpanStarts("text", "!!!"), Error, "wordless query rejected");
assert.throws(() => wordSpanStarts("text", 5), Error, "non-string query rejected");
assert.throws(() => wordSpanStarts(null, "cat"), Error, "non-string passage rejected");
console.log("ok");
