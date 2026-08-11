import assert from "node:assert/strict";
import { pairSums } from "./solution.ts";

assert.deepEqual(pairSums([1, 2, 3]), [3, 5], "three readings, two pairs");
assert.deepEqual(pairSums([1, 2]), [3], "one pair");
assert.deepEqual(pairSums([5]), [], "one reading holds no pair");
assert.deepEqual(pairSums([]), [], "no readings at all");
assert.deepEqual(pairSums([0, 0, 0]), [0, 0], "nothing adds to nothing");
assert.deepEqual(pairSums([1, -1, 2]), [0, 1], "a pair may cancel out");
console.log("ok");
