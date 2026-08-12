import assert from "node:assert/strict";
import { daysFor, planDays } from "./solution.ts";

assert.equal(daysFor(10, 5), 2, "an exact number of days");
assert.equal(daysFor(11, 5), 3, "a part day counts as one");
assert.equal(daysFor(0, 5), 0, "no work, no days");
assert.deepEqual(planDays([10, 11], 5), [2, 3], "a plan for two jobs");
assert.deepEqual(planDays([], 5), [], "no jobs at all");
assert.throws(() => daysFor(10, 0), Error, "a rate of zero is rejected");
console.log("ok");
