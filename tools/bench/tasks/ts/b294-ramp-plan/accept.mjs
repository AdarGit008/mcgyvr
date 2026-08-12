import assert from "node:assert/strict";
import { rampStep, rampPlan } from "./solution.ts";

assert.equal(rampStep(0, 10, 3), 3, "a full step toward the target");
assert.equal(rampStep(9, 10, 3), 10, "the last step never overshoots");
assert.equal(rampStep(10, 0, 4), 6, "stepping downward");
assert.deepEqual(rampPlan(0, 6, 2), [0, 2, 4, 6], "an exact climb");
assert.deepEqual(rampPlan(0, 5, 2), [0, 2, 4, 5], "a short final step");
assert.deepEqual(rampPlan(3, 3, 1), [3], "already there");
assert.deepEqual(rampPlan(5, 2, 1), [5, 4, 3, 2], "a descent");
console.log("ok");
