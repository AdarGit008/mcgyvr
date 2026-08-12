import assert from "node:assert/strict";
import { minGap } from "./solution.ts";

assert.equal(minGap([1, 9, 2]), 1, "the closest pair is not adjacent");
assert.equal(minGap([5, 1]), 4, "two values, one gap");
assert.equal(minGap([3]), -1, "one value has no gap");
assert.equal(minGap([]), -1, "no values at all");
assert.equal(minGap([4, 4]), 0, "two equal values are no distance apart");
assert.equal(minGap([10, 1, 5, 2]), 1, "order does not matter");
console.log("ok");
