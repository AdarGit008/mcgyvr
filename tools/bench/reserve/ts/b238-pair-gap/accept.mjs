import assert from "node:assert/strict";
import { pairGap } from "./solution.ts";

assert.deepEqual(pairGap([1, 5, 3, 4]), [3, 4], "the closest pair after sorting");
assert.deepEqual(pairGap([10, 1]), [1, 10], "two values are the pair");
assert.deepEqual(pairGap([1, 2, 3]), [1, 2], "a tie goes to the earlier pair");
assert.deepEqual(pairGap([5, 5]), [5, 5], "a repeated value has no gap");
assert.deepEqual(pairGap([-3, -1, 10]), [-3, -1], "negatives sort first");
assert.throws(() => pairGap([1]), Error, "one value cannot pair");
assert.throws(() => pairGap([]), Error, "no values cannot pair");
console.log("ok");
