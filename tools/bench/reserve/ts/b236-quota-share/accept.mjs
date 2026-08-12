import assert from "node:assert/strict";
import { quotaShare } from "./solution.ts";

assert.deepEqual(quotaShare(10, [1, 1]), [5, 5], "an even split");
assert.deepEqual(quotaShare(10, [3, 1]), [8, 2], "the leftover follows the weight");
assert.deepEqual(quotaShare(7, [1, 1, 1]), [3, 2, 2], "one unit left over");
assert.deepEqual(quotaShare(5, [0, 0]), [0, 0], "no weight, no claim");
assert.deepEqual(quotaShare(0, [1, 2]), [0, 0], "nothing to hand out");
assert.deepEqual(quotaShare(9, [2, 1]), [6, 3], "an exact proportion");
console.log("ok");
