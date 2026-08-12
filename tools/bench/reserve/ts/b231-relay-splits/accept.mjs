import assert from "node:assert/strict";
import { relaySplits } from "./solution.ts";

assert.deepEqual(relaySplits([12, 25, 40]), [12, 13, 15], "three legs");
assert.deepEqual(relaySplits([9]), [9], "the first leg is the first reading");
assert.deepEqual(relaySplits([]), [], "no legs run");
assert.deepEqual(relaySplits([1, 2, 3]), [1, 1, 1], "even legs");
assert.throws(() => relaySplits([10, 10]), Error, "a stalled clock is rejected");
assert.throws(() => relaySplits([10, 4]), Error, "a clock going backwards is rejected");
console.log("ok");
