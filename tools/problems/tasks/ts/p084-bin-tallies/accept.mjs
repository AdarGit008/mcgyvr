import assert from "node:assert/strict";
import { binTallies } from "./solution.ts";

assert.deepEqual(
  binTallies([1, 5, 7, 12], [0, 5, 10]),
  { bands: [1, 2], below: 0, above: 1 },
  "readings spread over bands and overflow",
);
assert.deepEqual(
  binTallies([5], [0, 5, 10]),
  { bands: [0, 1], below: 0, above: 0 },
  "a reading on an inner edge lands in the upper band",
);
assert.deepEqual(
  binTallies([0], [0, 5, 10]),
  { bands: [1, 0], below: 0, above: 0 },
  "a reading on the first edge is inside, not below",
);
assert.deepEqual(
  binTallies([10], [0, 5, 10]),
  { bands: [0, 0], below: 0, above: 1 },
  "a reading on the last edge is above, not inside",
);
assert.deepEqual(
  binTallies([-1, -50], [0, 5, 10]),
  { bands: [0, 0], below: 2, above: 0 },
  "readings under the first edge count as below",
);
assert.deepEqual(
  binTallies([], [3, 9]),
  { bands: [0], below: 0, above: 0 },
  "no readings, all zero",
);
assert.deepEqual(
  binTallies([-5, -2], [-10, -3, 0]),
  { bands: [1, 1], below: 0, above: 0 },
  "negative edges work like any others",
);
assert.throws(() => binTallies([1], [4]), Error, "one edge is rejected");
assert.throws(() => binTallies([1], [0, 5, 5]), Error, "a repeated edge is rejected");
assert.throws(() => binTallies([1], [5, 3]), Error, "decreasing edges are rejected");
console.log("ok");
