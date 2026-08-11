import assert from "node:assert/strict";
import { fitBudget } from "./solution.ts";

assert.equal(fitBudget([3, 1, 2], 4), 2, "the two cheapest fit");
assert.equal(fitBudget([5], 4), 0, "nothing is affordable");
assert.equal(fitBudget([], 10), 0, "nothing on offer");
assert.equal(fitBudget([1, 1, 1], 3), 3, "everything fits exactly");
assert.equal(fitBudget([2, 2], 0), 0, "no money to spend");
assert.throws(() => fitBudget([1], -1), Error, "a negative budget is rejected");
console.log("ok");
