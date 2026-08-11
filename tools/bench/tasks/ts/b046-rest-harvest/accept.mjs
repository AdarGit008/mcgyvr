import assert from "node:assert/strict";
import { bestHarvest } from "./solution.ts";

assert.equal(bestHarvest([]), 0, "no days yields zero");
assert.equal(bestHarvest([7]), 7, "a single day is taken whole");
assert.equal(bestHarvest([4, 9]), 9, "adjacent days keep only the better");
assert.equal(bestHarvest([5, 1, 1, 5]), 10, "the ends beat any middle pick");
assert.equal(bestHarvest([3, 2, 5, 10, 7]), 15, "alternating picks add up");
assert.equal(bestHarvest([1, 20, 3, 4, 25, 2]), 45, "two heavy days with rest between");
assert.equal(bestHarvest([0, 0, 0]), 0, "all-zero days yield zero");
assert.throws(() => bestHarvest(42), Error, "non-list is rejected");
assert.throws(() => bestHarvest([3, -1]), Error, "negative yield is rejected");
assert.throws(() => bestHarvest([1, 2.5]), Error, "fractional yield is rejected");
console.log("ok");
