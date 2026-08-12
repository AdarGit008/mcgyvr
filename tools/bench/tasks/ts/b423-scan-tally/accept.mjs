import assert from "node:assert/strict";
import { stepValue, scanTally } from "./solution.ts";

assert.equal(stepValue("+"), 1, "a plus adds one");
assert.equal(stepValue("-"), -1, "a minus takes one away");
assert.equal(stepValue("x"), 0, "anything else adds nothing");
assert.deepEqual(scanTally(["+", "+"]), [1, 2], "a total after each step");
assert.deepEqual(scanTally([]), [], "no instructions at all");
assert.deepEqual(scanTally(["+", "-", "+"]), [1, 0, 1], "the total moves both ways");
console.log("ok");
