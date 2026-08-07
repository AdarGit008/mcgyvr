import assert from "node:assert/strict";
import { runBufferedLine } from "./solution.ts";

assert.deepEqual(
  runBufferedLine([5, 3], [4], 3),
  { made: 6, left: [4] },
  "two stations: warm-up tick then steady flow of 3",
);
assert.deepEqual(
  runBufferedLine([2, 5, 1], [3, 2], 4),
  { made: 2, left: [3, 2] },
  "three stations: the slow tail backs the line up",
);
assert.deepEqual(
  runBufferedLine([1, 1], [1], 3),
  { made: 2, left: [1] },
  "downstream-first order: a piece needs a full tick per hop",
);
assert.deepEqual(
  runBufferedLine([10, 1], [2], 4),
  { made: 3, left: [2] },
  "a full buffer blocks the eager upstream station",
);
assert.deepEqual(
  runBufferedLine([4], [], 3),
  { made: 12, left: [] },
  "a single station just streams stock to the bin",
);
assert.deepEqual(
  runBufferedLine([3, 3], [5], 0),
  { made: 0, left: [0] },
  "zero ticks moves nothing",
);
assert.throws(() => runBufferedLine([], [], 2), Error, "empty line is rejected");
assert.throws(
  () => runBufferedLine([2, 2], [], 2),
  Error,
  "missing buffer is rejected",
);
assert.throws(
  () => runBufferedLine([2, 0], [1], 2),
  Error,
  "zero per-tick limit is rejected",
);
assert.throws(
  () => runBufferedLine([2, 2], [1.5], 2),
  Error,
  "fractional buffer size is rejected",
);
assert.throws(
  () => runBufferedLine([2, 2], [1], -1),
  Error,
  "negative tick count is rejected",
);
console.log("ok");
