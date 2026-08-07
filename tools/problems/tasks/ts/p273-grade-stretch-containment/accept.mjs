import assert from "node:assert/strict";
import { gradeContainment } from "./solution.ts";

assert.equal(
  gradeContainment(["the", "cat", "sat", "on", "the", "mat"], ["the", "cat", "sat"], 2),
  1000,
  "every draft stretch is present",
);
assert.equal(
  gradeContainment(["a", "b", "a", "b"], ["a", "b", "a", "b", "a", "b"], 2),
  600,
  "copies run out",
);
assert.equal(
  gradeContainment(["x", "y"], ["x", "y", "z", "w"], 2),
  333,
  "one of three, truncated",
);
assert.equal(
  gradeContainment(["m", "n"], ["p", "q", "m", "n"], 2),
  333,
  "the closing stretch counts",
);
assert.equal(gradeContainment([], ["a", "b"], 2), 0, "an empty source grades nought");
assert.equal(
  gradeContainment(["red", "blue"], ["red", "red", "blue"], 1),
  666,
  "single words, one repeat unspent",
);
assert.equal(
  gradeContainment(["a", "b", "c", "d"], ["a", "b", "c"], 3),
  1000,
  "stretches of three",
);
assert.equal(
  gradeContainment(["q", "r", "s"], ["t", "u", "v"], 2),
  0,
  "nothing carried over",
);
assert.throws(
  () => gradeContainment(["a", "b"], ["a", "b"], 0),
  Error,
  "span nought is rejected",
);
assert.throws(
  () => gradeContainment(["a", "b"], ["a", "b"], 1.5),
  Error,
  "a fractional span is rejected",
);
assert.throws(
  () => gradeContainment("ab", ["a", "b"], 2),
  Error,
  "a source that is not a list is rejected",
);
assert.throws(
  () => gradeContainment(["a", 5], ["a", "b"], 2),
  Error,
  "a source element that is not a word is rejected",
);
assert.throws(
  () => gradeContainment(["a", "b"], ["a", ""], 2),
  Error,
  "an empty word is rejected",
);
assert.throws(
  () => gradeContainment(["a", "b", "c"], ["a", "b"], 3),
  Error,
  "a draft shorter than span is rejected",
);
console.log("ok");
