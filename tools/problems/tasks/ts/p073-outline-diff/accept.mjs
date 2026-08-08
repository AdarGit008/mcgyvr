import assert from "node:assert/strict";
import { outlineDiff } from "./solution.ts";

assert.deepEqual(outlineDiff({}, {}), [], "empty outlines");

assert.deepEqual(
  outlineDiff({ a: {} }, { a: {} }),
  [],
  "identical outlines"
);

assert.deepEqual(
  outlineDiff({}, { b: {}, a: {} }),
  ["added a", "added b"],
  "top-level adds come out sorted"
);

assert.deepEqual(
  outlineDiff({ ch1: { intro: {} } }, { ch1: { intro: {}, notes: {} } }),
  ["added ch1/notes"],
  "shared headings are descended into"
);

assert.deepEqual(
  outlineDiff({ ch1: { old: { deep: {} } } }, { ch1: {} }),
  ["removed ch1/old"],
  "a removed branch is exactly one line"
);

assert.deepEqual(
  outlineDiff({ a: { x: {} }, b: {} }, { a: { y: {} }, c: {} }),
  ["added a/y", "added c", "removed a/x", "removed b"],
  "mixed nested adds and removes, sorted"
);

console.log("ok");
