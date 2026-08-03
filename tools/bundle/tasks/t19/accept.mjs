import assert from "node:assert/strict";
import { safeDivide } from "./solution.ts";

assert.equal(safeDivide(6, 3), 2, "ordinary division");
assert.equal(safeDivide(-6, 3), -2, "a negative numerator");
assert.equal(safeDivide(0, 5), 0, "zero divided by something");
assert.equal(safeDivide(1, 8), 0.125, "a fractional result");

assert.throws(() => safeDivide(1, 0), Error, "division by zero throws");
assert.throws(() => safeDivide(1, -0), Error, "negative zero is still zero");

for (const bad of [NaN, Infinity, -Infinity]) {
  assert.throws(() => safeDivide(bad, 1), Error, `numerator ${String(bad)} throws`);
  assert.throws(() => safeDivide(1, bad), Error, `divisor ${String(bad)} throws`);
}

// JavaScript will divide by a boolean. The contract says it must not.
assert.throws(() => safeDivide(true, 1), Error, "a boolean numerator is not a number");
assert.throws(() => safeDivide(1, true), Error, "a boolean divisor is not a number");
assert.throws(() => safeDivide("6", 3), Error, "a numeric string is not a number");
assert.throws(() => safeDivide(null, 1), Error, "null is not a number");
