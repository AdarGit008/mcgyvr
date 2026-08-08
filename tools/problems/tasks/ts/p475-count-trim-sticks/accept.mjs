import assert from "node:assert/strict";
import { countTrimSticks } from "./solution.ts";

assert.deepEqual(
  countTrimSticks(100, [40, 40, 30], 3),
  { sticks: 2, tails: [14, 67] },
  "a call too long for the bench stick fetches a fresh one",
);

assert.deepEqual(
  countTrimSticks(100, [], 3),
  { sticks: 0, tails: [] },
  "a run with no calls fetches nothing",
);

assert.deepEqual(
  countTrimSticks(10, [10], 2),
  { sticks: 1, tails: [0] },
  "a call as long as the stick leaves it carrying nothing",
);

assert.deepEqual(
  countTrimSticks(12, [5, 5, 5], 0),
  { sticks: 2, tails: [2, 7] },
  "a bladeless saw still runs the stick out",
);

assert.deepEqual(
  countTrimSticks(8, [8, 8], 5),
  { sticks: 2, tails: [0, 0] },
  "two full-length calls take two sticks",
);

assert.deepEqual(
  countTrimSticks(20, [3, 3, 3], 1),
  { sticks: 1, tails: [8] },
  "short calls all come off one stick",
);

assert.deepEqual(
  countTrimSticks(30, [30, 1], 0),
  { sticks: 2, tails: [0, 29] },
  "a spent stick is set aside rather than kept for a shorter call",
);

assert.throws(
  () => countTrimSticks(0, [1], 0),
  Error,
  "a stick below one is rejected",
);
assert.throws(
  () => countTrimSticks(1.5, [1], 0),
  Error,
  "a stick that is not whole is rejected",
);
assert.throws(
  () => countTrimSticks(10, "40", 0),
  Error,
  "a calls argument that is not a list is rejected",
);
assert.throws(
  () => countTrimSticks(10, [0], 0),
  Error,
  "a call below one is rejected",
);
assert.throws(
  () => countTrimSticks(10, [2.5], 0),
  Error,
  "a call that is not whole is rejected",
);
assert.throws(
  () => countTrimSticks(20, [5, 21], 0),
  Error,
  "a call longer than a fresh stick is rejected",
);
assert.throws(
  () => countTrimSticks(10, [1], -1),
  Error,
  "a blade below nought is rejected",
);
assert.throws(
  () => countTrimSticks(10, [1], 0.5),
  Error,
  "a blade that is not whole is rejected",
);
console.log("ok");
