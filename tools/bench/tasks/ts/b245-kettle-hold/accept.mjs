import assert from "node:assert/strict";
import { kettleHold } from "./solution.ts";

assert.equal(kettleHold([90, 95, 96], 95), 2, "the tail that held");
assert.equal(kettleHold([96, 96], 95), 2, "the whole run held");
assert.equal(kettleHold([90], 95), 0, "never reached the target");
assert.equal(kettleHold([], 95), 0, "no readings at all");
assert.equal(kettleHold([95, 90, 95], 95), 1, "an earlier dip does not count");
assert.equal(kettleHold([100, 100, 100], 50), 3, "well above throughout");
console.log("ok");
