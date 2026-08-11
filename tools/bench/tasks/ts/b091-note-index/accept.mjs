import assert from "node:assert/strict";
import { buildWordIndex, wordsOfLine } from "./solution.ts";

assert.deepEqual(
  wordsOfLine("Ship-Shape, 2nd try!"),
  ["ship", "shape", "2nd", "try"],
  "the helper splits and lowercases",
);
assert.deepEqual(wordsOfLine("..."), [], "the helper finds nothing in punctuation");
assert.deepEqual(buildWordIndex("tea time"), { tea: [1], time: [1] }, "one line, two words");
assert.deepEqual(
  buildWordIndex("tea tea tea"),
  { tea: [1] },
  "a word repeating on a line lists it once",
);
assert.deepEqual(
  buildWordIndex("milk\nmilk sugar\nsugar"),
  { milk: [1, 2], sugar: [2, 3] },
  "line numbers accumulate in increasing order",
);
assert.deepEqual(
  buildWordIndex("jam\n\njam"),
  { jam: [1, 3] },
  "a blank line still counts in the numbering",
);
assert.deepEqual(buildWordIndex("Tea\nTEA tea"), { tea: [1, 2] }, "case folds before indexing");
assert.deepEqual(buildWordIndex(""), {}, "an empty note has an empty index");
assert.deepEqual(buildWordIndex("\n\n"), {}, "blank lines alone index nothing");
assert.deepEqual(
  buildWordIndex("to-do: buy jam\nbuy milk, buy bread"),
  { to: [1], do: [1], buy: [1, 2], jam: [1], milk: [2], bread: [2] },
  "punctuation separates words on every line",
);
assert.throws(() => buildWordIndex(42), Error, "a number is rejected");
assert.throws(() => buildWordIndex(null), Error, "null is rejected");
assert.throws(() => buildWordIndex(["tea"]), Error, "a list is rejected");
console.log("ok");
