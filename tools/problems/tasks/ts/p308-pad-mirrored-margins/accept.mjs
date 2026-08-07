import assert from "node:assert/strict";
import { padMirroredMargins } from "./solution.ts";

const run = [4, 7, 9];

assert.deepEqual(
  padMirroredMargins(run, 0, 0),
  [4, 7, 9],
  "no margins leaves the run alone",
);
assert.deepEqual(
  padMirroredMargins(run, 1, 0),
  [4, 4, 7, 9],
  "the first reading appears twice at the near glass",
);
assert.deepEqual(
  padMirroredMargins(run, 0, 1),
  [4, 7, 9, 9],
  "the last reading appears twice at the far glass",
);
assert.deepEqual(
  padMirroredMargins(run, 2, 2),
  [7, 4, 4, 7, 9, 9, 7],
  "two on each side",
);
assert.deepEqual(
  padMirroredMargins(run, 3, 3),
  [9, 7, 4, 4, 7, 9, 9, 7, 4],
  "margins as long as the run itself",
);
assert.deepEqual(
  padMirroredMargins(run, 7, 0),
  [4, 4, 7, 9, 9, 7, 4, 4, 7, 9],
  "a margin longer than the run bounces twice",
);
assert.deepEqual(
  padMirroredMargins([5], 3, 2),
  [5, 5, 5, 5, 5, 5],
  "a run of one reading repeats forever",
);
assert.deepEqual(
  padMirroredMargins([-2, 0, 5], 1, 1),
  [-2, -2, 0, 5, 5],
  "negative readings mirror like any other",
);
assert.deepEqual(
  padMirroredMargins([0, 1], 1, 1),
  [0, 0, 1, 1],
  "a run of two reflects across both glasses",
);
assert.deepEqual(
  padMirroredMargins([1, 2, 3, 4], 5, 5),
  [4, 4, 3, 2, 1, 1, 2, 3, 4, 4, 3, 2, 1, 1],
  "five each side of a run of four",
);
assert.throws(
  () => padMirroredMargins([], 1, 1),
  Error,
  "an empty run is rejected",
);
assert.throws(
  () => padMirroredMargins("479", 1, 1),
  Error,
  "a string is not a run",
);
assert.throws(
  () => padMirroredMargins([4, 7.5], 1, 1),
  Error,
  "a fractional reading is rejected",
);
assert.throws(
  () => padMirroredMargins([4, "7"], 1, 1),
  Error,
  "a lettered reading is rejected",
);
assert.throws(
  () => padMirroredMargins(run, -1, 1),
  Error,
  "a negative margin is rejected",
);
assert.throws(
  () => padMirroredMargins(run, 1, 1.5),
  Error,
  "a fractional margin is rejected",
);
assert.throws(
  () => padMirroredMargins(run, null, 1),
  Error,
  "a missing margin is rejected",
);
console.log("ok");
