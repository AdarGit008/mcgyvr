import assert from "node:assert/strict";
import { fillBetween } from "./solution.ts";

assert.deepEqual(fillBetween(["a", "b"], "-"), ["a", "-", "b"], "one filler");
assert.deepEqual(
  fillBetween(["a", "b", "c"], "-"),
  ["a", "-", "b", "-", "c"],
  "three entries give five",
);
assert.deepEqual(fillBetween(["a"], "-"), ["a"], "one entry takes no filler");
assert.deepEqual(fillBetween([], "-"), [], "an empty list");
assert.deepEqual(fillBetween(["a", "b"], ""), ["a", "", "b"], "an empty filler");
assert.deepEqual(
  fillBetween(["x", "y", "z"], "|"),
  ["x", "|", "y", "|", "z"],
  "another filler",
);
console.log("ok");
