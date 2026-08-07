import assert from "node:assert/strict";
import { minimaxPairSum } from "./solution.ts";

assert.equal(minimaxPairSum([1, 2, 3], [1, 2, 3]), 4, "beats in-order pairing's 6");
const left = [5, 1, 8];
const right = [3, 9, 2];
assert.equal(minimaxPairSum(left, right), 10, "small carries the big partner");
assert.deepEqual(left, [5, 1, 8], "first list is left unmodified");
assert.deepEqual(right, [3, 9, 2], "second list is left unmodified");
assert.equal(minimaxPairSum([-5, 0, 5], [10, -10, 0]), 5, "negatives absorb peaks");
assert.equal(minimaxPairSum([7], [7]), 14, "single pair has no choice");
assert.equal(minimaxPairSum([4, 4, 4, 4], [1, 2, 3, 4]), 8, "duplicates on one side");
assert.throws(() => minimaxPairSum([1, 2], [1]), Error, "unequal lengths rejected");
assert.throws(() => minimaxPairSum([], []), Error, "empty lists rejected");
assert.throws(() => minimaxPairSum([1, 2.5], [3, 4]), Error, "fractional entry rejected");
assert.throws(() => minimaxPairSum([1, 2], [3, "4"]), Error, "string entry rejected");
console.log("ok");
