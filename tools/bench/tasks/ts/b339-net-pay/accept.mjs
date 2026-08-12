import assert from "node:assert/strict";
import { netPay } from "./solution.ts";

assert.equal(netPay(1000, 10, 50), 850, "the rate comes off first");
assert.equal(netPay(1000, 0, 50), 950, "no rate, just the fee");
assert.equal(netPay(100, 10, 0), 90, "no fee, just the rate");
assert.equal(netPay(100, 50, 100), 0, "pay never falls below zero");
assert.equal(netPay(0, 10, 0), 0, "nothing earned, nothing paid");
assert.equal(netPay(999, 10, 0), 900, "the rate is rounded down");
console.log("ok");
