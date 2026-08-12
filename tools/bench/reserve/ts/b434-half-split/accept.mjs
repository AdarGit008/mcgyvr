import assert from "node:assert/strict";
import { halfSplit } from "./solution.ts";

assert.deepEqual(halfSplit(["a", "b"]), [["a"], ["b"]], "an even split");
assert.deepEqual(
  halfSplit(["a", "b", "c"]),
  [["a", "b"], ["c"]],
  "the spare goes to the first half",
);
assert.deepEqual(halfSplit([]), [[], []], "two empty halves");
assert.deepEqual(halfSplit(["a"]), [["a"], []], "one entry is all first half");
assert.deepEqual(
  halfSplit(["a", "b", "c", "d"]),
  [["a", "b"], ["c", "d"]],
  "four split evenly",
);
assert.deepEqual(halfSplit(["a", "b", "c", "d", "e"]), [["a", "b", "c"], ["d", "e"]], "five");
console.log("ok");
