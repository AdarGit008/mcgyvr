import assert from "node:assert/strict";
import { stepCost, tripCost } from "./solution.ts";

assert.equal(stepCost(10, 3), 30, "distance times rate");
assert.equal(stepCost(0, 3), 0, "no distance, no cost");
assert.equal(tripCost([10, 10], 3, 50), 60, "the hops add up past the minimum");
assert.equal(tripCost([1, 1], 3, 50), 50, "a cheap trip pays the minimum once");
assert.equal(tripCost([], 3, 50), 50, "an empty trip still pays it");
assert.equal(tripCost([100], 3, 50), 300, "one long hop");
console.log("ok");
