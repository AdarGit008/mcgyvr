import assert from "node:assert/strict";
import { meetingPoints } from "./solution.ts";

assert.deepEqual(
  meetingPoints(0, 4, 0, 6, 3),
  [0, 12, 24],
  "two ladders from the same start meet on their least common multiple",
);
assert.deepEqual(
  meetingPoints(1, 4, 3, 6, 3),
  [9, 21, 33],
  "offset starts with strides sharing a factor",
);
assert.deepEqual(
  meetingPoints(10, 3, 4, 5, 2),
  [19, 34],
  "the earliest landing sits at or beyond both starts",
);
assert.deepEqual(
  meetingPoints(5, 1, 0, 1, 3),
  [5, 6, 7],
  "strides of one meet everywhere at or beyond the later start",
);
assert.deepEqual(
  meetingPoints(7, 7, 7, 7, 4),
  [7, 14, 21, 28],
  "two identical ladders meet at every rung",
);
assert.deepEqual(
  meetingPoints(0, 2, 1, 4, 5),
  [],
  "an even ladder and an odd one never land together",
);
assert.deepEqual(
  meetingPoints(0, 4, 0, 6, 0),
  [],
  "a count of nothing asks for no landings at all",
);
assert.deepEqual(
  meetingPoints(1, 4, 3, 6, 1),
  [9],
  "a count of one hands back just the earliest landing",
);
assert.deepEqual(
  meetingPoints(0, 100000, 0, 99999, 2),
  [0, 9999900000],
  "strides at the ceiling still land exactly",
);

assert.throws(() => meetingPoints(0, 0, 0, 4, 2), Error, "a stride of nothing is rejected");
assert.throws(() => meetingPoints(0, 4, 0, -6, 2), Error, "a negative stride is rejected");
assert.throws(
  () => meetingPoints(0, 100001, 0, 4, 2),
  Error,
  "a stride past the ceiling is rejected",
);
assert.throws(() => meetingPoints(-1, 4, 0, 6, 2), Error, "a negative start is rejected");
assert.throws(
  () => meetingPoints(1000001, 4, 0, 6, 2),
  Error,
  "a start past the ceiling is rejected",
);
assert.throws(() => meetingPoints(0, 4, 0, 6, 21), Error, "a count past twenty is rejected");
assert.throws(() => meetingPoints(0, 4, 0, 6, -1), Error, "a negative count is rejected");
assert.throws(() => meetingPoints(0.5, 4, 0, 6, 2), Error, "a fractional start is rejected");
assert.throws(() => meetingPoints("0", 4, 0, 6, 2), Error, "a non-numeric start is rejected");
console.log("ok");
