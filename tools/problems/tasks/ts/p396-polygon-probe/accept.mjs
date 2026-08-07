import assert from "node:assert/strict";
import { polygonProbe } from "./solution.ts";

assert.deepEqual(
  polygonProbe(
    [
      [0, 0],
      [1, 0],
      [1, 1],
      [0, 1],
    ],
    [
      [0, 0],
      [1, 1],
      [2, 2],
    ],
  ),
  { doubled: 2, marks: ["edge", "edge", "outside"] },
  "one unit cell doubles to 2 and its corners rest on the line",
);

assert.deepEqual(
  polygonProbe(
    [
      [0, 0],
      [4, 0],
      [4, 4],
      [0, 4],
    ],
    [
      [2, 2],
      [0, 2],
      [2, 0],
      [4, 4],
      [5, 5],
      [-1, 2],
    ],
  ),
  {
    doubled: 32,
    marks: ["inside", "edge", "edge", "edge", "outside", "outside"],
  },
  "a four-wide square, its sides, its corner, and two spots beyond it",
);

assert.deepEqual(
  polygonProbe(
    [
      [0, 0],
      [4, 0],
      [0, 3],
    ],
    [
      [1, 1],
      [2, 1],
      [2, 0],
      [4, 3],
      [3, 1],
    ],
  ),
  { doubled: 12, marks: ["inside", "inside", "edge", "outside", "outside"] },
  "the 4 by 3 triangle, with a spot just past its slant",
);

assert.deepEqual(
  polygonProbe(
    [
      [0, 3],
      [4, 0],
      [0, 0],
    ],
    [[1, 1]],
  ),
  { doubled: 12, marks: ["inside"] },
  "walking the same triangle the other way round changes nothing",
);

assert.deepEqual(
  polygonProbe(
    [
      [0, 0],
      [4, 0],
      [4, 4],
      [2, 2],
      [0, 4],
    ],
    [
      [2, 1],
      [3, 2],
      [2, 3],
      [3, 3],
      [1, 3],
    ],
  ),
  {
    doubled: 24,
    marks: ["inside", "inside", "outside", "edge", "edge"],
  },
  "a notched ring: the notch is outside, its walls are edges",
);

assert.deepEqual(
  polygonProbe(
    [
      [-2, -2],
      [2, -2],
      [2, 2],
      [-2, 2],
    ],
    [
      [0, 0],
      [-2, 0],
      [-3, 0],
    ],
  ),
  { doubled: 32, marks: ["inside", "edge", "outside"] },
  "negative measures behave the same",
);

assert.deepEqual(
  polygonProbe(
    [
      [0, 0],
      [2, 0],
      [5, 0],
    ],
    [
      [1, 0],
      [3, 0],
      [6, 0],
      [1, 1],
    ],
  ),
  { doubled: 0, marks: ["edge", "edge", "outside", "outside"] },
  "a flattened ring shuts in nothing but still has a line",
);

assert.deepEqual(
  polygonProbe(
    [
      [0, 0],
      [3, 0],
      [3, 3],
    ],
    [],
  ),
  { doubled: 9, marks: [] },
  "no sample spots leaves the verdicts empty",
);

assert.throws(
  () => polygonProbe([[0, 0], [1, 1]], []),
  Error,
  "two corners are not a ring",
);
assert.throws(
  () => polygonProbe([[0, 0], [0, 0], [1, 1]], []),
  Error,
  "neighbouring corners that repeat are rejected",
);
assert.throws(
  () => polygonProbe([[0, 0], [2, 0], [1, 1], [0, 0]], []),
  Error,
  "writing the opening corner again at the tail is rejected",
);
assert.throws(
  () => polygonProbe([[0, 0], [2, 0], [1, 0.5]], []),
  Error,
  "a fractional corner is rejected",
);
assert.throws(
  () => polygonProbe([[0, 0], [2, 0], [0, 2]], [[1, "1"]]),
  Error,
  "a text measure in a sample spot is rejected",
);
assert.throws(
  () => polygonProbe([[0, 0], [200001, 0], [0, 2]], []),
  Error,
  "an oversized measure is rejected",
);
assert.throws(
  () => polygonProbe([[0, 0], [2, 0], [0, 2]], "spots"),
  Error,
  "a non-list of sample spots is rejected",
);
console.log("ok");
