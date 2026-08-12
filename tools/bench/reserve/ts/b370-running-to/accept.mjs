import assert from "node:assert/strict";
import { runningTo } from "./solution.ts";

assert.equal(runningTo([1, 2, 3], 1), 3, "the named position is included");
assert.equal(runningTo([1, 2, 3], 0), 1, "the first position alone");
assert.equal(runningTo([1, 2, 3], 9), 6, "past the end totals everything");
assert.equal(runningTo([1, 2, 3], -1), 0, "below zero totals nothing");
assert.equal(runningTo([], 0), 0, "an empty list");
assert.equal(runningTo([5], 0), 5, "a single entry");
console.log("ok");
