import assert from "node:assert/strict";
import { smoothWithTaps } from "./solution.ts";

const series = [1, 2, 3, 4, 5];

assert.deepEqual(
  smoothWithTaps(series, [1]),
  [1, 2, 3, 4, 5],
  "a lone weight of one copies the series",
);
assert.deepEqual(
  smoothWithTaps(series, [0, 1, 0]),
  [1, 2, 3, 4, 5],
  "a window that only reads its middle copies the series",
);
assert.deepEqual(
  smoothWithTaps(series, [1, 1, 1]),
  [5, 6, 9, 12, 13],
  "a three-wide sum hinges at both ends",
);
assert.deepEqual(
  smoothWithTaps(series, [1, 0, -1]),
  [0, -2, -2, -2, 0],
  "a difference window flattens to nought at the hinges",
);
assert.deepEqual(
  smoothWithTaps(series, [1, 1, 1, 1, 1]),
  [11, 12, 15, 18, 19],
  "a five-wide sum reaches two places past each end",
);
assert.deepEqual(
  smoothWithTaps([7], [1, 1, 1]),
  [21],
  "a single sample swallows the whole window",
);
assert.deepEqual(
  smoothWithTaps([1, 2], [1, 1, 1]),
  [5, 4],
  "a series of two alternates as it hinges",
);
assert.deepEqual(
  smoothWithTaps([-1, 0, 1], [1, 1, 1]),
  [-1, 0, 1],
  "negative samples hinge like any other",
);
assert.deepEqual(
  smoothWithTaps([4, 4, 4], [2]),
  [8, 8, 8],
  "a single weight scales every sample",
);
assert.throws(
  () => smoothWithTaps([], [1]),
  Error,
  "an empty series is rejected",
);
assert.throws(
  () => smoothWithTaps("123", [1]),
  Error,
  "a string is not a series",
);
assert.throws(
  () => smoothWithTaps([1, 2.5], [1]),
  Error,
  "a fractional sample is rejected",
);
assert.throws(
  () => smoothWithTaps(series, "1"),
  Error,
  "a string is not a weight list",
);
assert.throws(
  () => smoothWithTaps(series, []),
  Error,
  "an empty weight list is rejected",
);
assert.throws(
  () => smoothWithTaps(series, [1, 0.5, 1]),
  Error,
  "a fractional weight is rejected",
);
assert.throws(
  () => smoothWithTaps(series, [1, 1]),
  Error,
  "an even count of weights has no middle",
);
console.log("ok");
