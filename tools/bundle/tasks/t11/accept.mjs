import assert from "node:assert/strict";
import { sortAscending } from "./solution.ts";

assert.deepEqual(sortAscending([10, 9, 100]), [9, 10, 100], "the bug: text order, not numeric");
assert.deepEqual(sortAscending([2, 1, 3]), [1, 2, 3], "already-small numbers");
assert.deepEqual(sortAscending([]), [], "empty input");
assert.deepEqual(sortAscending([5]), [5], "single element");
assert.deepEqual(sortAscending([1, 2, 3]), [1, 2, 3], "already sorted");
assert.deepEqual(sortAscending([3, 3, 1]), [1, 3, 3], "duplicates");
assert.deepEqual(sortAscending([-5, 2, -10]), [-10, -5, 2], "negative numbers");
assert.deepEqual(sortAscending([0.5, 0.25, 1]), [0.25, 0.5, 1], "fractions");

const input = [3, 1, 2];
const snapshot = JSON.stringify(input);
sortAscending(input);
assert.equal(JSON.stringify(input), snapshot, "the argument must not be mutated");
