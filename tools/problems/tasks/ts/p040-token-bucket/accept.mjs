import assert from "node:assert/strict";
import { tokenBucket } from "./solution.ts";

assert.deepEqual(
  tokenBucket(10, 2, [[0, 4], [1, 8], [2, 3], [5, 7], [5, 1]]),
  ["grant", "grant", "refuse", "grant", "grant"],
  "accrual, a refusal, and a same-instant follow-up",
);
assert.deepEqual(
  tokenBucket(5, 1, [[0, 3], [0, 3], [10, 5]]),
  ["grant", "refuse", "grant"],
  "no accrual within one instant and the top-up is capped",
);
assert.deepEqual(
  tokenBucket(3, 5, [[0, 4], [1, 3]]),
  ["refuse", "grant"],
  "a cost above capacity is refused even when full",
);
assert.deepEqual(
  tokenBucket(2, 0, [[0, 1], [100, 2], [100, 1], [101, 1]]),
  ["grant", "refuse", "grant", "refuse"],
  "a zero refill rate never restores anything",
);
assert.deepEqual(
  tokenBucket(4, 3, [[2, 4], [3, 4], [4, 4]]),
  ["grant", "refuse", "grant"],
  "a refusal leaves the balance untouched for the next accrual",
);
assert.deepEqual(tokenBucket(5, 2, []), [], "an empty log has no labels");
assert.throws(() => tokenBucket(0, 1, []), Error, "zero capacity is rejected");
assert.throws(() => tokenBucket(5, -1, []), Error, "negative refill is rejected");
assert.throws(() => tokenBucket(5, 1, [[0, 0]]), Error, "zero cost is rejected");
assert.throws(() => tokenBucket(5, 1, [[-1, 1]]), Error, "negative arrival time is rejected");
assert.throws(
  () => tokenBucket(5, 1, [[5, 1], [4, 1]]),
  Error,
  "a backwards arrival is rejected",
);
console.log("ok");
