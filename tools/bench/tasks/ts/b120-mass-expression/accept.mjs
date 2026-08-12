import assert from "node:assert/strict";
import { massExpression } from "./solution.ts";

assert.equal(massExpression("2kg + 300g", "g"), 2300, "kilograms and grams add up");
assert.equal(massExpression("0g", "g"), 0, "a zero tally counts zero");
assert.equal(massExpression("1t - 200kg", "kg"), 800, "a draw comes off the tonne");
assert.equal(
  massExpression("1g - 1g + 5kg", "kg"),
  5,
  "the tally may touch zero and refill",
);
assert.equal(
  massExpression("3kg + 500g + 500g", "kg"),
  4,
  "a whole total converts upward",
);
assert.throws(() => massExpression(42, "g"), Error, "a non-string tally is rejected");
assert.throws(() => massExpression("", "g"), Error, "an empty tally is rejected");
assert.throws(
  () => massExpression("1g +", "g"),
  Error,
  "a tally ending on an operator is rejected",
);
assert.throws(() => massExpression("2kg+300g", "g"), Error, "missing spaces are rejected");
assert.throws(() => massExpression("02g", "g"), Error, "a leading zero is rejected");
assert.throws(() => massExpression("2lb", "g"), Error, "an unknown unit is rejected");
assert.throws(() => massExpression("1g * 2g", "g"), Error, "an unknown operator is rejected");
assert.throws(
  () => massExpression("3g - 5g + 4g", "g"),
  Error,
  "dipping below zero is rejected",
);
assert.throws(() => massExpression("500g", "lb"), Error, "an unknown goal unit is rejected");
assert.throws(() => massExpression("1500g", "kg"), Error, "a fractional total is rejected");
console.log("ok");
