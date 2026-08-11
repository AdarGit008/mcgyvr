import assert from "node:assert/strict";
import { lowOf, orderPairs } from "./solution.ts";

assert.equal(lowOf([3, 1]), 1, "the smaller of the two");
assert.equal(lowOf([2, 2]), 2, "a pair of the same");
assert.deepEqual(
  orderPairs([[5, 9], [1, 100]]),
  [[1, 100], [5, 9]],
  "ordered by the smaller number",
);
assert.deepEqual(orderPairs([]), [], "no pairs at all");
assert.deepEqual(orderPairs([[1, 2]]), [[1, 2]], "a single pair");
assert.deepEqual(
  orderPairs([[1, 9], [1, 3]]),
  [[1, 9], [1, 3]],
  "a tie leaves the earlier pair earlier",
);
console.log("ok");
