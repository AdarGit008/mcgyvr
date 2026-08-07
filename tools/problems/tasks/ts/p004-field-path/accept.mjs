import assert from "node:assert/strict";
import { splitFieldPath } from "./solution.ts";

assert.deepEqual(splitFieldPath("a"), ["a"], "single identifier");
assert.deepEqual(
  splitFieldPath("items[0].tags[2]"),
  ["items", 0, "tags", 2],
  "identifiers and integer indexes interleave",
);
assert.deepEqual(splitFieldPath("a.b.c"), ["a", "b", "c"], "dotted chain");
assert.deepEqual(splitFieldPath("m[10][3]"), ["m", 10, 3], "stacked indexes");
assert.deepEqual(
  splitFieldPath("_x9[0].y_z"),
  ["_x9", 0, "y_z"],
  "underscores in identifiers",
);
assert.throws(() => splitFieldPath(""), Error, "empty string is rejected");
assert.throws(() => splitFieldPath(".a"), Error, "leading dot is rejected");
assert.throws(() => splitFieldPath("a."), Error, "trailing dot is rejected");
assert.throws(() => splitFieldPath("a[]"), Error, "empty brackets are rejected");
assert.throws(() => splitFieldPath("a[3"), Error, "unterminated bracket is rejected");
assert.throws(() => splitFieldPath("a[03]"), Error, "leading zero index is rejected");
assert.throws(() => splitFieldPath("a[+3]"), Error, "signed index is rejected");
assert.throws(() => splitFieldPath("9a"), Error, "identifier starting with digit");
assert.throws(() => splitFieldPath("a..b"), Error, "doubled dot is rejected");
assert.throws(() => splitFieldPath(7), Error, "non-string is rejected");
console.log("ok");
