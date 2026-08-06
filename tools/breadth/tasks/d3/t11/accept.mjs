import assert from "node:assert/strict";
import { diff } from "./solution.ts";

assert.deepEqual(diff(["a"], ["a"]), [], "equal single lines");
assert.deepEqual(diff([], []), [], "both empty");
assert.deepEqual(diff(["a", "b"], ["a", "b"]), [], "equal arrays");

assert.deepEqual(
  diff(["a"], ["b"]),
  ["@@ -1,1 +1,1 @@", "-a", "+b"],
  "single replacement",
);
assert.deepEqual(
  diff(["x"], ["x", "y"]),
  ["@@ -1,0 +2,1 @@", "+y"],
  "append after the last kept line",
);
assert.deepEqual(
  diff(["m"], ["a", "m"]),
  ["@@ -0,0 +1,1 @@", "+a"],
  "insertion before everything uses start 0",
);
assert.deepEqual(
  diff(["x"], ["x", "x"]),
  ["@@ -0,0 +1,1 @@", "+x"],
  "duplicate-line tie resolves to an insertion before the match",
);
assert.deepEqual(
  diff(["p", "q"], []),
  ["@@ -1,2 +0,0 @@", "-p", "-q"],
  "deleting every line",
);
assert.deepEqual(
  diff([], ["p"]),
  ["@@ -0,0 +1,1 @@", "+p"],
  "inserting into an empty file",
);
assert.deepEqual(
  diff(["1", "2", "3"], ["1", "x", "3"]),
  ["@@ -2,1 +2,1 @@", "-2", "+x"],
  "replacement in the middle",
);
assert.deepEqual(
  diff(["1", "2", "3", "4", "5"], ["1", "x", "3", "4", "y"]),
  ["@@ -2,1 +2,1 @@", "-2", "+x", "@@ -5,1 +5,1 @@", "-5", "+y"],
  "two separate hunks with correct line numbers",
);
assert.deepEqual(
  diff(["a", "b", "c"], ["x", "b", "y"]),
  ["@@ -1,1 +1,1 @@", "-a", "+x", "@@ -3,1 +3,1 @@", "-c", "+y"],
  "hunks on both sides of a kept line",
);
assert.deepEqual(
  diff(["a", "b"], ["b", "a"]),
  ["@@ -1,1 +0,0 @@", "-a", "@@ -2,0 +2,1 @@", "+a"],
  "swap under the pinned tie rule",
);
assert.deepEqual(
  diff(["h", "d1", "d2", "t"], ["h", "i1", "i2", "i3", "t"]),
  ["@@ -2,2 +2,3 @@", "-d1", "-d2", "+i1", "+i2", "+i3"],
  "one hunk lists all deletions before all insertions",
);
