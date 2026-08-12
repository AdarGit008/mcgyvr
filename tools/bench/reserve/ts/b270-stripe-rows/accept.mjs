import assert from "node:assert/strict";
import { stripeRows } from "./solution.ts";

assert.deepEqual(stripeRows(2, ["red", "blue"]), ["red", "blue"], "one pass");
assert.deepEqual(
  stripeRows(5, ["red", "blue"]),
  ["red", "blue", "red", "blue", "red"],
  "the list starts again",
);
assert.deepEqual(stripeRows(1, ["red", "blue", "green"]), ["red"], "a short wall");
assert.deepEqual(stripeRows(0, ["red"]), [], "no rows, no colours");
assert.deepEqual(stripeRows(3, ["grey"]), ["grey", "grey", "grey"], "one colour repeats");
assert.deepEqual(stripeRows(4, ["a", "b", "c"]), ["a", "b", "c", "a"], "wrapping mid-list");
console.log("ok");
