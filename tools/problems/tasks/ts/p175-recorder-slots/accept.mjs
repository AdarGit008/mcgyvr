import assert from "node:assert/strict";
import { recorderSnapshot } from "./solution.ts";

assert.deepEqual(
  recorderSnapshot(3, [10, 11, 12, 13]),
  { order: [11, 12, 13], head: 1, overwritten: 1, starved: 0 },
  "one write past the end drops the oldest frame and moves the marker",
);
assert.deepEqual(
  recorderSnapshot(3, [10, 11, -1, 12, 13, 14]),
  { order: [12, 13, 14], head: 2, overwritten: 1, starved: 0 },
  "an eject partway through shifts where later writes land",
);
assert.deepEqual(
  recorderSnapshot(2, [-1, -1, 5]),
  { order: [5], head: 0, overwritten: 0, starved: 2 },
  "ejects against an empty recorder are tallied, not applied",
);
assert.deepEqual(
  recorderSnapshot(1, [7, 8, 9]),
  { order: [9], head: 0, overwritten: 2, starved: 0 },
  "a single slot keeps only the newest frame",
);
assert.deepEqual(
  recorderSnapshot(4, []),
  { order: [], head: 0, overwritten: 0, starved: 0 },
  "an empty script leaves the recorder untouched",
);
assert.deepEqual(
  recorderSnapshot(3, [1, 2, 3, 4, 5, -1, -1]),
  { order: [5], head: 1, overwritten: 2, starved: 0 },
  "ejects after a wrap leave the marker mid-cycle",
);
assert.deepEqual(
  recorderSnapshot(2, [4, 5, -1, -1, -1, 6]),
  { order: [6], head: 0, overwritten: 0, starved: 1 },
  "a drained recorder writes to the slot the marker already points at",
);
assert.deepEqual(
  recorderSnapshot(4, [1, 2, 3, 4, 5, 6]),
  { order: [3, 4, 5, 6], head: 2, overwritten: 2, starved: 0 },
  "the surviving frames read oldest first even when the cycle has turned",
);
assert.deepEqual(
  recorderSnapshot(3, [0, 0, 0, 0]),
  { order: [0, 0, 0], head: 1, overwritten: 1, starved: 0 },
  "frame zero is an ordinary frame number",
);

assert.throws(() => recorderSnapshot(0, [1]), Error, "a zero slot count is rejected");
assert.throws(() => recorderSnapshot(2.5, [1]), Error, "a fractional slot count is rejected");
assert.throws(() => recorderSnapshot(2, "12"), Error, "a non-list script is rejected");
assert.throws(() => recorderSnapshot(2, [-2]), Error, "an entry below -1 is rejected");
assert.throws(() => recorderSnapshot(2, [1.5]), Error, "a fractional frame is rejected");
assert.throws(() => recorderSnapshot(2, ["3"]), Error, "a frame given as text is rejected");
console.log("ok");
