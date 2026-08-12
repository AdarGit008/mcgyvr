import assert from "node:assert/strict";
import { centsOf } from "./solution.ts";

assert.equal(centsOf("12"), 1200, "a bare whole part reads as whole cents");
assert.equal(centsOf("1,234.5"), 123450, "one decimal digit counts tenths");
assert.equal(centsOf("-0.07"), -7, "a minus sign turns the count negative");
assert.equal(centsOf("1234.56"), 123456, "an ungrouped whole part with two decimals");
assert.equal(centsOf("1,000,000"), 100000000, "several groups of three read as one number");
assert.throws(() => centsOf("12,34"), Error, "a group of the wrong width is rejected");
assert.throws(() => centsOf(42), Error, "an amount that is not a string is rejected");
console.log("ok");
