import assert from "node:assert/strict";
import { driftCheck } from "./solution.ts";

assert.equal(driftCheck([1, 2, 9], 3), 2, "the jump is found");
assert.equal(driftCheck([1, 2, 3], 3), -1, "every step is small enough");
assert.equal(driftCheck([5, 1], 3), 1, "a fall drifts too");
assert.equal(driftCheck([5], 1), -1, "one reading cannot drift");
assert.equal(driftCheck([], 1), -1, "no readings at all");
assert.equal(driftCheck([1, 4, 10, 2], 3), 2, "a step on the allowance is fine");
console.log("ok");
