import assert from "node:assert/strict";
import { stepRate, rateSteps } from "./solution.ts";

assert.equal(stepRate(1000, 50, 10), 150, "the fixed sum and a tenth");
assert.equal(stepRate(0, 50, 10), 50, "nothing but the fixed sum");
assert.equal(stepRate(999, 0, 10), 99, "the share is rounded down");
assert.deepEqual(rateSteps([1000, 0], 50, 10), [150, 50], "two amounts charged");
assert.deepEqual(rateSteps([], 50, 10), [], "no amounts at all");
assert.equal(stepRate(100, 0, 0), 0, "no fixed sum and no share");
console.log("ok");
