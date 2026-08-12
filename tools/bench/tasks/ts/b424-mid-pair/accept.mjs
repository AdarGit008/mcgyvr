import assert from "node:assert/strict";
import { midPair } from "./solution.ts";

assert.deepEqual(midPair([1, 2, 3, 4]), [2, 3], "the two middle values");
assert.deepEqual(midPair([1, 2, 3]), [2, 2], "an odd length gives one twice");
assert.deepEqual(midPair([]), [0, 0], "nothing at all");
assert.deepEqual(midPair([5]), [5, 5], "one value is its own middle");
assert.deepEqual(midPair([4, 1, 3, 2]), [2, 3], "the list is put in order first");
assert.deepEqual(midPair([9, 1]), [1, 9], "two values are both middle");
console.log("ok");
