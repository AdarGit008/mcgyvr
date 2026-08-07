import assert from "node:assert/strict";
import { pourToTarget } from "./solution.ts";

assert.deepEqual(pourToTarget([5], 0), [], "nothing to do when zero is wanted");
assert.deepEqual(pourToTarget([5], 5), ["fill A"], "one vessel, one fill");
assert.equal(pourToTarget([5], 3), null, "a lone vessel cannot split itself");
assert.deepEqual(pourToTarget([3, 5], 3), ["fill A"], "fills come first");
assert.deepEqual(pourToTarget([3, 5], 5), ["fill B"], "second vessel filled");
assert.deepEqual(
  pourToTarget([3, 5], 2),
  ["fill B", "pour B A"],
  "the remainder left behind after a pour",
);
assert.deepEqual(
  pourToTarget([3, 5], 4),
  ["fill B", "pour B A", "empty A", "pour B A", "fill B", "pour B A"],
  "six actions for four litres",
);
assert.deepEqual(
  pourToTarget([1, 2, 3], 3),
  ["fill C"],
  "the third vessel is labelled C",
);
assert.equal(pourToTarget([2, 4], 3), null, "even vessels never leave an odd amount");
assert.equal(pourToTarget([3, 5], 7), null, "more than any vessel can hold");
assert.throws(() => pourToTarget([], 1), Error, "no vessels is rejected");
assert.throws(() => pourToTarget([0, 5], 5), Error, "a capacity of zero is rejected");
assert.throws(() => pourToTarget([2.5, 5], 5), Error, "a fractional capacity is rejected");
assert.throws(() => pourToTarget([3, 5], -1), Error, "a negative amount is rejected");
console.log("ok");
