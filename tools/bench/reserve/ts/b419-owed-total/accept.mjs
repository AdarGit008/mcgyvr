import assert from "node:assert/strict";
import { owedTotal } from "./solution.ts";

assert.equal(owedTotal([10, 20]), 30, "two charges add up");
assert.equal(owedTotal([10, -4]), 6, "a payment reduces the total");
assert.equal(owedTotal([]), 0, "an empty ledger");
assert.equal(owedTotal([5, -5]), 0, "paid off exactly");
assert.equal(owedTotal([100, -30, -20]), 50, "two payments against a charge");
assert.throws(() => owedTotal([-1]), Error, "an overpaid ledger is rejected");
console.log("ok");
