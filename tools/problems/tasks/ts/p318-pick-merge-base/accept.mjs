import assert from "node:assert/strict";
import { pickMergeBase } from "./solution.ts";

const history = {
  a: [],
  b: ["a"],
  c: ["a"],
  d: ["b", "c"],
  e: ["b"],
  f: ["c"],
};
const crossed = {
  r: [],
  x: ["r"],
  y: ["r"],
  m: ["x", "y"],
  n: ["y", "x"],
};

assert.equal(pickMergeBase(history, "e", "f"), "a", "two lines meet at the root");
assert.equal(pickMergeBase(history, "b", "c"), "a", "siblings meet at the root");
assert.equal(pickMergeBase(history, "d", "e"), "b", "the nearer forebear wins");
assert.equal(pickMergeBase(history, "b", "e"), "b", "a forebear of one is the answer");
assert.equal(pickMergeBase(history, "d", "d"), "d", "a revision against itself");
assert.equal(pickMergeBase(history, "a", "f"), "a", "the root against a leaf");
assert.equal(pickMergeBase(crossed, "m", "n"), "x", "alphabetical order settles a tie");
assert.equal(pickMergeBase(crossed, "m", "r"), "r", "the root is the only shared one");
assert.throws(
  () => pickMergeBase({ p: [], q: [] }, "p", "q"),
  Error,
  "unrelated roots share nothing",
);
assert.throws(() => pickMergeBase(history, "a", "zz"), Error, "an unknown revision");
assert.throws(() => pickMergeBase({ a: ["z"] }, "a", "a"), Error, "an unknown parent");
assert.throws(
  () => pickMergeBase({ a: [], b: ["a", "a"] }, "a", "b"),
  Error,
  "the same parent named twice",
);
assert.throws(
  () => pickMergeBase({ u: ["v"], v: ["u"] }, "u", "v"),
  Error,
  "a revision descending from itself",
);
assert.throws(() => pickMergeBase({ a: "b" }, "a", "a"), Error, "a parent list that is not a list");
assert.throws(() => pickMergeBase([], "a", "a"), Error, "a history that is not a mapping");
console.log("ok");
