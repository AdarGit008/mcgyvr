import assert from "node:assert/strict";
import { removeNegatives } from "./solution.ts";

// Adjacent negatives are what the splice-while-iterating bug drops.
assert.deepEqual(removeNegatives([1, -1, -2, 2]), [1, 2], "adjacent negatives both go");
assert.deepEqual(removeNegatives([-1, -2, -3]), [], "every element removed");
assert.deepEqual(removeNegatives([1, 2, 3]), [1, 2, 3], "nothing to remove");
assert.deepEqual(removeNegatives([]), [], "empty input");
assert.deepEqual(removeNegatives([-1]), [], "single negative");
assert.deepEqual(removeNegatives([0, -0, 1]), [0, -0, 1], "zero is not negative");
assert.deepEqual(removeNegatives([-1, 1, -2, 2, -3, 3]), [1, 2, 3], "alternating");

const input = [1, -1, 2];
const snapshot = JSON.stringify(input);
const result = removeNegatives(input);
assert.equal(JSON.stringify(input), snapshot, "the argument must not be mutated");
assert.notEqual(result, input, "a new array is returned");
