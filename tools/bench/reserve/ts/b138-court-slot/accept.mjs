import assert from "node:assert/strict";
import { reserveCourt } from "./solution.ts";

assert.deepEqual(reserveCourt([], [60, 120], [0, 600]), [[60, 120]], "empty sheet");
assert.deepEqual(
  reserveCourt([[0, 60], [180, 240]], [90, 150], [0, 600]),
  [[0, 60], [90, 150], [180, 240]],
  "slot lands between bookings",
);
assert.deepEqual(
  reserveCourt([[0, 60]], [60, 90], [0, 600]),
  [[0, 60], [60, 90]],
  "touching a booking's end is allowed",
);
assert.deepEqual(
  reserveCourt([[120, 180]], [60, 120], [0, 600]),
  [[60, 120], [120, 180]],
  "touching a booking's start is allowed",
);
assert.deepEqual(
  reserveCourt([[0, 60], [90, 120]], [60, 90], [0, 600]),
  [[0, 60], [60, 90], [90, 120]],
  "a slot may touch on both sides",
);
assert.deepEqual(reserveCourt([], [0, 600], [0, 600]), [[0, 600]], "whole day fits");
assert.deepEqual(
  reserveCourt([[300, 360], [0, 60]], [120, 180], [0, 600]),
  [[0, 60], [120, 180], [300, 360]],
  "bookings arrive unsorted",
);
const sheet = [[300, 360], [0, 60]];
reserveCourt(sheet, [120, 180], [0, 600]);
assert.deepEqual(sheet, [[300, 360], [0, 60]], "the given sheet is untouched");
assert.throws(() => reserveCourt([[50, 100]], [90, 150], [0, 600]), Error, "overlap rejected");
assert.throws(() => reserveCourt([[0, 200]], [50, 100], [0, 600]), Error, "contained slot rejected");
assert.throws(() => reserveCourt([], [30, 90], [60, 600]), Error, "slot before opening rejected");
assert.throws(() => reserveCourt([], [540, 660], [0, 600]), Error, "slot past closing rejected");
assert.throws(() => reserveCourt([], [10.5, 60], [0, 600]), Error, "fractional bound rejected");
assert.throws(() => reserveCourt([], [120, 60], [0, 600]), Error, "reversed slot rejected");
assert.throws(() => reserveCourt([], [60, 120], [600, 0]), Error, "reversed hours rejected");
assert.throws(
  () => reserveCourt([[0, 100], [50, 150]], [200, 260], [0, 600]),
  Error,
  "overlapping sheet rejected",
);
assert.throws(() => reserveCourt([[0]], [200, 260], [0, 600]), Error, "one-item booking rejected");
assert.throws(() => reserveCourt([[60, 0]], [200, 260], [0, 600]), Error, "reversed booking rejected");
console.log("ok");
