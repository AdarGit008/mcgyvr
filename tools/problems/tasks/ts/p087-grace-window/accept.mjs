import assert from "node:assert/strict";
import { graceWindow } from "./solution.ts";

assert.equal(graceWindow([100, 0, 100], 100, 1), 3, "one grace day bridges the gap");
assert.equal(graceWindow([100, 0, 100], 100, 0), 1, "no grace, no bridge");
assert.equal(graceWindow([100, 100, 0, 0, 100], 100, 1), 2, "two misses exceed one grace day");
assert.equal(graceWindow([100, 100, 0, 0, 100], 100, 2), 5, "two grace days bridge both");
assert.equal(
  graceWindow([0, 100, 0, 0, 0, 100, 0], 100, 3),
  5,
  "the stretch must start and end on kept days",
);
assert.equal(graceWindow([1, 2, 3], 10, 5), 0, "no kept day means zero");
assert.equal(graceWindow([5, 5, 5], 5, 0), 3, "reaching the goal exactly keeps the day");
assert.equal(graceWindow([7, 0, 7, 7, 0, 0, 7], 7, 1), 4, "grace is spent per stretch, not per gap");
assert.equal(graceWindow([], 3, 2), 0, "an empty log has no stretch");
assert.throws(() => graceWindow([1], 0, 1), Error, "a non-positive goal is rejected");
assert.throws(() => graceWindow([1], 5, -1), Error, "negative grace is rejected");
console.log("ok");
