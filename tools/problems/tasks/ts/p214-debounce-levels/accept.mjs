import assert from "node:assert/strict";
import { debounceLevels } from "./solution.ts";

assert.deepEqual(debounceLevels([1], 3), [1], "a single sample settles itself");
assert.deepEqual(
  debounceLevels([0, 1, 1, 0, 1, 1, 1, 0], 1),
  [0, 1, 1, 0, 1, 1, 1, 0],
  "a hold of one believes everything"
);
assert.deepEqual(
  debounceLevels([0, 1, 1, 0, 1, 1, 1, 0], 2),
  [0, 0, 1, 1, 1, 1, 1, 1],
  "two samples in a row are believed"
);
assert.deepEqual(
  debounceLevels([1, 0, 0, 0, 1], 3),
  [1, 1, 1, 0, 0],
  "the flip lands on the sample that completes the run"
);
assert.deepEqual(
  debounceLevels([0, 1, 1, 1, 1], 5),
  [0, 0, 0, 0, 0],
  "a run that never reaches hold changes nothing"
);
assert.deepEqual(
  debounceLevels([0, 1, 0, 1, 0, 1], 2),
  [0, 0, 0, 0, 0, 0],
  "chatter clears the tally every other sample"
);
assert.deepEqual(
  debounceLevels([0, 0, 0], 2),
  [0, 0, 0],
  "a quiet line stays put"
);
assert.deepEqual(
  debounceLevels([1, 0, 0, 1, 1, 0, 0], 2),
  [1, 1, 0, 0, 1, 1, 0],
  "the level flips back and forth when each run is long enough"
);

assert.throws(
  () => debounceLevels("0101", 2),
  Error,
  "a sample list that is not a list is rejected"
);
assert.throws(() => debounceLevels([], 2), Error, "an empty line is rejected");
assert.throws(
  () => debounceLevels([0, 2, 1], 2),
  Error,
  "a sample outside 0 and 1 is rejected"
);
assert.throws(
  () => debounceLevels([0, "1"], 2),
  Error,
  "a sample that is not a number is rejected"
);
assert.throws(
  () => debounceLevels([0, 1], 0),
  Error,
  "a hold of zero is rejected"
);
assert.throws(
  () => debounceLevels([0, 1], -3),
  Error,
  "a negative hold is rejected"
);
assert.throws(
  () => debounceLevels([0, 1], 2.5),
  Error,
  "a hold that is not whole is rejected"
);

console.log("ok");
