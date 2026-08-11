import assert from "node:assert/strict";
import { batonRace } from "./solution.ts";

assert.equal(batonRace([10, 10], 2), 22, "two legs pay one handover");
assert.equal(batonRace([1, 2, 3], 1), 8, "three legs pay two handovers");
assert.equal(batonRace([7, 3], 5), 15, "a costlier handover");
assert.equal(batonRace([5], 3), 5, "a lone leg pays no handover");
assert.equal(batonRace([4, 4, 4, 4], 0), 16, "a handover that costs nothing");
assert.equal(batonRace([], 4), 0, "a race with no legs");
console.log("ok");
