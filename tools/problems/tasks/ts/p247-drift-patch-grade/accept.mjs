import assert from "node:assert/strict";
import { gradeTolerantPatches } from "./solution.ts";

assert.deepEqual(
  gradeTolerantPatches([[4]], 0),
  { count: 1, sizes: [1], seeds: [0] },
  "a plate of one cell",
);
assert.deepEqual(
  gradeTolerantPatches(
    [
      [10, 10],
      [10, 10],
    ],
    0,
  ),
  { count: 1, sizes: [4], seeds: [0] },
  "one flat patch",
);
assert.deepEqual(
  gradeTolerantPatches([[1, 3, 5]], 2),
  { count: 1, sizes: [3], seeds: [0] },
  "a slope holds together step by step",
);
assert.deepEqual(
  gradeTolerantPatches([[1, 3, 5]], 1),
  { count: 3, sizes: [1, 1, 1], seeds: [0, 1, 2] },
  "too small a drift breaks every link",
);
assert.deepEqual(
  gradeTolerantPatches([[0, 2, 4, 6]], 2),
  { count: 1, sizes: [4], seeds: [0] },
  "a longer slope still holds together",
);
assert.deepEqual(
  gradeTolerantPatches(
    [
      [1, 9],
      [9, 1],
    ],
    0,
  ),
  { count: 2, sizes: [2, 2], seeds: [0, 1] },
  "cells meeting only at a corner are linked",
);
assert.deepEqual(
  gradeTolerantPatches(
    [
      [5, 6, 20],
      [7, 8, 21],
    ],
    1,
  ),
  { count: 2, sizes: [4, 2], seeds: [0, 2] },
  "a corner step carries the chain across lines",
);
assert.deepEqual(
  gradeTolerantPatches(
    [
      [1, 1, 9],
      [1, 9, 9],
    ],
    0,
  ),
  { count: 2, sizes: [3, 3], seeds: [0, 2] },
  "patches of equal size go by earliest cell",
);
assert.throws(() => gradeTolerantPatches("plate", 0), Error, "a non-list plate is rejected");
assert.throws(() => gradeTolerantPatches([], 0), Error, "a plate with no lines is rejected");
assert.throws(() => gradeTolerantPatches([[]], 0), Error, "a line with no cells is rejected");
assert.throws(() => gradeTolerantPatches(["ab"], 0), Error, "a line that is not a list is rejected");
assert.throws(
  () => gradeTolerantPatches([[1], [1, 2]], 0),
  Error,
  "lines of unequal length are rejected",
);
assert.throws(() => gradeTolerantPatches([[1, null]], 0), Error, "a non-number reading is rejected");
assert.throws(() => gradeTolerantPatches([[1, 2]], -1), Error, "a negative drift is rejected");
assert.throws(() => gradeTolerantPatches([[1, 2]], 0.5), Error, "a fractional drift is rejected");
console.log("ok");
