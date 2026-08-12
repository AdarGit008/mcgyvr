import assert from "node:assert/strict";
import { hourRate, weekPay } from "./solution.ts";

assert.equal(hourRate(10), 10, "an hour is worth the rate");
assert.equal(weekPay(40, 10), 400, "exactly the normal week");
assert.equal(weekPay(42, 10), 430, "only the extra hours are dearer");
assert.equal(weekPay(0, 10), 0, "no hours, no pay");
assert.equal(weekPay(41, 10), 415, "one hour of overtime");
assert.equal(weekPay(10, 5), 50, "a short week");
console.log("ok");
