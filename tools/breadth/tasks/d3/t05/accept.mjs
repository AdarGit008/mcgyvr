import assert from "node:assert/strict";
import { skyline } from "./solution.ts";

assert.deepEqual(
  skyline([[2, 9, 10], [3, 7, 15], [5, 12, 12], [15, 20, 10], [19, 24, 8]]),
  [[2, 10], [3, 15], [7, 12], [12, 0], [15, 10], [20, 8], [24, 0]],
  "classic overlapping skyline",
);
assert.deepEqual(
  skyline([[0, 2, 3], [2, 5, 3]]),
  [[0, 3], [5, 0]],
  "touching equal heights merge with no seam point",
);
assert.deepEqual(
  skyline([[1, 10, 5], [3, 6, 3]]),
  [[1, 5], [10, 0]],
  "a nested shorter building is invisible",
);
assert.deepEqual(
  skyline([[1, 10, 5], [3, 6, 8]]),
  [[1, 5], [3, 8], [6, 5], [10, 0]],
  "a nested taller building pokes out and drops back",
);
assert.deepEqual(
  skyline([[0, 2, 3], [5, 7, 4]]),
  [[0, 3], [2, 0], [5, 4], [7, 0]],
  "a gap returns to the ground between buildings",
);
assert.deepEqual(
  skyline([[0, 3, 3], [0, 5, 2]]),
  [[0, 3], [3, 2], [5, 0]],
  "shared left edge keeps only the taller start",
);
assert.deepEqual(
  skyline([[2, 5, 1], [4, 5, 4]]),
  [[2, 1], [4, 4], [5, 0]],
  "shared right edge drops straight to the ground",
);
assert.deepEqual(
  skyline([[1, 2, 1], [1, 2, 1]]),
  [[1, 1], [2, 0]],
  "duplicate buildings collapse to one outline",
);
assert.deepEqual(
  skyline([[0, 1, 1], [1, 2, 2], [2, 3, 1]]),
  [[0, 1], [1, 2], [2, 1], [3, 0]],
  "staircase up and down",
);
assert.deepEqual(skyline([]), [], "no buildings");
