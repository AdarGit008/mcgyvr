import assert from "node:assert/strict";
import { labelValueRegions } from "./solution.ts";

assert.deepEqual(
  labelValueRegions([[1]]),
  { map: [[1]], sizes: [1], values: [1] },
  "a single square",
);
assert.deepEqual(
  labelValueRegions([
    [1, 1],
    [1, 1],
  ]),
  { map: [[1, 1], [1, 1]], sizes: [4], values: [1] },
  "one region filling the grid",
);
assert.deepEqual(
  labelValueRegions([
    [1, 2],
    [2, 1],
  ]),
  { map: [[1, 2], [3, 4]], sizes: [1, 1, 1, 1], values: [1, 2, 2, 1] },
  "corner touching does not join squares",
);
assert.deepEqual(
  labelValueRegions([[7, 7, 7]]),
  { map: [[1, 1, 1]], sizes: [3], values: [7] },
  "one row is one region",
);
assert.deepEqual(
  labelValueRegions([[1], [2], [1]]),
  { map: [[1], [2], [3]], sizes: [1, 1, 1], values: [1, 2, 1] },
  "one column of three regions",
);
assert.deepEqual(
  labelValueRegions([
    [5, 5, 0],
    [0, 5, 0],
    [0, 0, 0],
  ]),
  {
    map: [
      [1, 1, 2],
      [2, 1, 2],
      [2, 2, 2],
    ],
    sizes: [3, 6],
    values: [5, 0],
  },
  "a region that wraps around another",
);
assert.deepEqual(
  labelValueRegions([
    [-3, -3],
    [4, -3],
  ]),
  { map: [[1, 1], [2, 1]], sizes: [3, 1], values: [-3, 4] },
  "negative numbers join like any other",
);
assert.throws(() => labelValueRegions(5), Error, "a non-list grid is rejected");
assert.throws(() => labelValueRegions([]), Error, "a grid with no rows is rejected");
assert.throws(() => labelValueRegions([[]]), Error, "a row with no squares is rejected");
assert.throws(() => labelValueRegions(["ab"]), Error, "a row that is not a list is rejected");
assert.throws(
  () => labelValueRegions([[1], [1, 2]]),
  Error,
  "rows of unequal length are rejected",
);
assert.throws(() => labelValueRegions([[1, "a"]]), Error, "a non-number square is rejected");
assert.throws(() => labelValueRegions([[1, 2.5]]), Error, "a fractional square is rejected");
console.log("ok");
