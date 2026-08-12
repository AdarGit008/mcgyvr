import assert from "node:assert/strict";
import { throttleCalls } from "./solution.ts";

assert.deepEqual(throttleCalls([0, 1, 2], 5, 10), [true, true, true], "under the limit every call passes");
assert.deepEqual(throttleCalls([0, 1, 2], 2, 10), [true, true, false], "the burst stops at the limit");
assert.deepEqual(throttleCalls([0, 4], 1, 5), [true, false], "a call still inside the window counts");
assert.deepEqual(throttleCalls([0, 5], 1, 5), [true, true], "a call exactly window later stops counting");
assert.deepEqual(throttleCalls([0, 0, 1, 3], 2, 3), [true, true, false, true], "expiry frees the quota again");
assert.deepEqual(throttleCalls([0, 1, 2], 1, 2), [true, false, true], "a refused call never counts later");
assert.deepEqual(throttleCalls([], 3, 4), [], "no calls yields no verdicts");
assert.throws(() => throttleCalls("soon", 1, 1), Error, "a non-list of arrivals is rejected");
assert.throws(() => throttleCalls([0, 1.5], 1, 1), Error, "a fractional arrival is rejected");
assert.throws(() => throttleCalls([3, 1], 1, 1), Error, "decreasing arrivals are rejected");
assert.throws(() => throttleCalls([0], 0, 1), Error, "a zero limit is rejected");
assert.throws(() => throttleCalls([0], 1, 0), Error, "a zero window is rejected");
console.log("ok");
