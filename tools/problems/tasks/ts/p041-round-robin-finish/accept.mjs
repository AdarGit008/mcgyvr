import assert from "node:assert/strict";
import { roundRobinFinish } from "./solution.ts";

assert.deepEqual(
  roundRobinFinish([["a", 5], ["b", 2], ["c", 3]], 2),
  [["b", 4], ["c", 9], ["a", 10]],
  "partial final slices must not inflate the clock",
);
assert.deepEqual(
  roundRobinFinish([["x", 1]], 4),
  [["x", 1]],
  "a job shorter than the quantum finishes at its own burst",
);
assert.deepEqual(
  roundRobinFinish([["a", 3], ["b", 3]], 3),
  [["a", 3], ["b", 6]],
  "exact multiples finish on quantum boundaries",
);
assert.deepEqual(
  roundRobinFinish([["a", 4], ["b", 1]], 1),
  [["b", 2], ["a", 5]],
  "unit quantum interleaves the queue",
);
assert.deepEqual(
  roundRobinFinish([["a", 7]], 3),
  [["a", 7]],
  "a lone job accumulates only its own work",
);
assert.deepEqual(
  roundRobinFinish([["p", 1], ["q", 5], ["r", 1]], 2),
  [["p", 1], ["r", 4], ["q", 7]],
  "completion order follows the rotation",
);
assert.throws(() => roundRobinFinish([["a", 1]], 0), Error, "zero quantum is rejected");
assert.throws(() => roundRobinFinish([["a", 0]], 2), Error, "zero burst is rejected");
assert.throws(
  () => roundRobinFinish([["a", 1], ["a", 2]], 2),
  Error,
  "a duplicate job name is rejected",
);
assert.throws(() => roundRobinFinish([[7, 1]], 2), Error, "a non-string name is rejected");
console.log("ok");
