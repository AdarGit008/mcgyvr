import assert from "node:assert/strict";
import { assignBins } from "./solution.ts";

assert.deepEqual(
  assignBins([["logs", ["*.log"]]], ["a.log", "b.txt"]),
  { bins: { logs: ["a.log"] }, leftover: ["b.txt"] },
  "a leading-star pattern bins its matches",
);
assert.deepEqual(
  assignBins([["errs", ["err*"]]], ["err42", "warn7"]),
  { bins: { errs: ["err42"] }, leftover: ["warn7"] },
  "a trailing-star pattern bins its matches",
);
assert.deepEqual(
  assignBins([["exact", ["core"]]], ["core", "core2"]),
  { bins: { exact: ["core"] }, leftover: ["core2"] },
  "a starless pattern matches only its exact text",
);
assert.deepEqual(
  assignBins([["wrap", ["ab*ba"]]], ["abba", "abcba", "aba"]),
  { bins: { wrap: ["abba", "abcba"] }, leftover: ["aba"] },
  "middle-star literal parts must not overlap",
);
assert.deepEqual(
  assignBins([["first", ["a*"]], ["second", ["*z"]]], ["az"]),
  { bins: { first: ["az"], second: [] }, leftover: [] },
  "only the first matching rule takes the item",
);
assert.deepEqual(
  assignBins([["all", ["*"]]], ["", "x"]),
  { bins: { all: ["", "x"] }, leftover: [] },
  "a bare star matches everything in input order",
);
assert.deepEqual(
  assignBins([], ["a"]),
  { bins: {}, leftover: ["a"] },
  "no rules leaves every item over",
);
assert.throws(() => assignBins("x", []), Error, "non-list rules are rejected");
assert.throws(() => assignBins([["a"]], []), Error, "a one-item rule is rejected");
assert.throws(
  () => assignBins([["", ["x"]]], []),
  Error,
  "an empty rule name is rejected",
);
assert.throws(
  () => assignBins([["a", ["x"]], ["a", ["y"]]], []),
  Error,
  "a repeated rule name is rejected",
);
assert.throws(
  () => assignBins([["a", []]], []),
  Error,
  "an empty patterns list is rejected",
);
assert.throws(
  () => assignBins([["a", [""]]], []),
  Error,
  "an empty pattern is rejected",
);
assert.throws(
  () => assignBins([["a", ["x*y*"]]], []),
  Error,
  "a two-star pattern is rejected",
);
assert.throws(
  () => assignBins([["a", ["x"]]], [3]),
  Error,
  "a non-string item is rejected",
);
console.log("ok");
