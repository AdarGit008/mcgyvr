import assert from "node:assert/strict";
import { climbBudget } from "./solution.ts";

assert.equal(climbBudget(["10", "15", "20"]), 15, "paying the middle rung alone wins");
assert.equal(climbBudget([]), 0, "an empty board costs nothing");
assert.equal(climbBudget(["7"]), 0, "a lone rung is skipped");
assert.equal(climbBudget(["1", "2"]), 1, "the cheaper of the first two rungs is enough");
assert.equal(climbBudget(["1", "100", "1", "1", "1", "100", "1", "1", "100", "1"]), 6, "a long board dodges the dear rungs");
assert.equal(climbBudget(["0", "0", "5"]), 0, "free rungs leave the total at zero");
assert.throws(() => climbBudget(["3", "x"]), Error, "a toll not written as digits is rejected");
assert.throws(() => climbBudget(["05"]), Error, "a toll with a leading zero is rejected");
console.log("ok");
