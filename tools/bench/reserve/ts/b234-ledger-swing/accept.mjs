import assert from "node:assert/strict";
import { ledgerSwing } from "./solution.ts";

assert.equal(ledgerSwing([10, 14, 9]), 5, "the widest of two moves");
assert.equal(ledgerSwing([1, 10]), 9, "a rise counts");
assert.equal(ledgerSwing([10, 1]), 9, "a fall counts the same");
assert.equal(ledgerSwing([5]), 0, "one balance cannot swing");
assert.equal(ledgerSwing([]), 0, "no balances, no swing");
assert.equal(ledgerSwing([3, 3, 3]), 0, "a flat ledger");
assert.equal(ledgerSwing([0, -5, 2]), 7, "across zero");
console.log("ok");
