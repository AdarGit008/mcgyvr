import assert from "node:assert/strict";
import { throttleCalls } from "./solution.ts";

assert.deepEqual(
  throttleCalls(10, 5, 100, [[0, 2], [1, 2]]),
  { verdicts: ["pass", "pass"], remaining: 96 },
  "calls within cap and budget pass",
);
assert.deepEqual(
  throttleCalls(10, 5, 100, [[0, 3], [1, 3]]),
  { verdicts: ["pass", "drop"], remaining: 97 },
  "a call overfilling the window drops",
);
assert.deepEqual(
  throttleCalls(10, 5, 100, [[0, 5], [10, 5]]),
  { verdicts: ["pass", "pass"], remaining: 90 },
  "a call a full span later has left the window",
);
assert.deepEqual(
  throttleCalls(10, 5, 100, [[0, 5], [9, 5]]),
  { verdicts: ["pass", "drop"], remaining: 95 },
  "a call inside the span still counts against the cap",
);
assert.deepEqual(
  throttleCalls(10, 5, 100, [[0, 4], [2, 4], [3, 1]]),
  { verdicts: ["pass", "drop", "pass"], remaining: 95 },
  "a dropped call holds no units against later calls",
);
assert.deepEqual(
  throttleCalls(10, 100, 3, [[0, 2], [1, 2]]),
  { verdicts: ["pass", "drop"], remaining: 1 },
  "the budget stops what the window would allow",
);
assert.deepEqual(
  throttleCalls(10, 5, 0, [[0, 1]]),
  { verdicts: ["drop"], remaining: 0 },
  "a zero budget drops everything",
);
assert.deepEqual(
  throttleCalls(10, 5, 7, []),
  { verdicts: [], remaining: 7 },
  "no calls leave the budget whole",
);
assert.throws(() => throttleCalls(0, 5, 10, []), Error, "a zero span is rejected");
assert.throws(() => throttleCalls(10, 2.5, 10, []), Error, "a fractional cap is rejected");
assert.throws(() => throttleCalls(10, 5, -1, []), Error, "a negative budget is rejected");
assert.throws(() => throttleCalls(10, 5, 10, [[1]]), Error, "a lone time is rejected");
assert.throws(() => throttleCalls(10, 5, 10, [[-1, 1]]), Error, "a negative time is rejected");
assert.throws(() => throttleCalls(10, 5, 10, [[0, 0]]), Error, "zero units are rejected");
assert.throws(
  () => throttleCalls(10, 5, 10, [[5, 1], [4, 1]]),
  Error,
  "times must not decrease",
);
console.log("ok");
