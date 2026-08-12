import assert from "node:assert/strict";
import { tierCost } from "./solution.ts";

assert.equal(tierCost(5, 10, 2, 5), 10, "inside the allowance");
assert.equal(tierCost(10, 10, 2, 5), 20, "exactly on the allowance");
assert.equal(tierCost(12, 10, 2, 5), 30, "only the excess costs more");
assert.equal(tierCost(0, 10, 2, 5), 0, "no units, no cost");
assert.equal(tierCost(3, 0, 2, 5), 15, "no allowance at all");
assert.throws(() => tierCost(-1, 10, 2, 5), Error, "negative units are rejected");
console.log("ok");
