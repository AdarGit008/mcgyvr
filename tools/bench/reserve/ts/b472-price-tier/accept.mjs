import assert from "node:assert/strict";
import { tierCost } from "./solution.ts";

assert.equal(tierCost(0), 0, "a count of nothing costs nothing");
assert.equal(tierCost(1), 100, "a small charge is lifted to the floor");
assert.equal(tierCost(2), 100, "still under the floor");
assert.equal(tierCost(4), 200, "above the floor at the first rate");
assert.equal(tierCost(10), 400, "the rate steps down");
assert.equal(tierCost(50), 1500, "the rate steps down again");
console.log("ok");
