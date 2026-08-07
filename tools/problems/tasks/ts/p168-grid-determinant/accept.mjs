import assert from "node:assert/strict";
import { gridDeterminant } from "./solution.ts";

assert.equal(gridDeterminant([[7]]), 7, "one cell");
assert.equal(gridDeterminant([[0]]), 0, "one empty cell");
assert.equal(gridDeterminant([[3, 4], [5, 6]]), -2, "two rows");
assert.equal(gridDeterminant([[1, 2], [2, 4]]), 0, "two rows in proportion");
assert.equal(gridDeterminant([[-2, 3], [4, -6]]), 0, "negatives in proportion");
assert.equal(
  gridDeterminant([
    [1, 0, 0],
    [0, 1, 0],
    [0, 0, 1],
  ]),
  1,
  "the plain three-row grid",
);
assert.equal(
  gridDeterminant([
    [0, 1, 0],
    [1, 0, 0],
    [0, 0, 1],
  ]),
  -1,
  "two rows exchanged flips the sign",
);
assert.equal(
  gridDeterminant([
    [1, 2, 3],
    [4, 5, 6],
    [7, 8, 10],
  ]),
  -3,
  "three rows",
);
assert.equal(
  gridDeterminant([
    [1, 2, 3],
    [4, 5, 6],
    [7, 8, 9],
  ]),
  0,
  "three rows that stack flat",
);
assert.equal(
  gridDeterminant([
    [2, -3, 1],
    [2, 0, -1],
    [1, 4, 5],
  ]),
  49,
  "mixed signs",
);

assert.throws(() => gridDeterminant([]), Error, "no rows rejected");
assert.throws(() => gridDeterminant("g"), Error, "non-list rejected");
assert.throws(() => gridDeterminant([[1, 2], [3]]), Error, "ragged rows rejected");
assert.throws(
  () => gridDeterminant([[1, 2, 3], [4, 5, 6]]),
  Error,
  "non-square rejected",
);
assert.throws(
  () =>
    gridDeterminant([
      [1, 0, 0, 0],
      [0, 1, 0, 0],
      [0, 0, 1, 0],
      [0, 0, 0, 1],
    ]),
  Error,
  "four rows rejected",
);
assert.throws(() => gridDeterminant([[1, 2], [3, 4.5]]), Error, "fraction rejected");
assert.throws(() => gridDeterminant([[1, "a"], [2, 3]]), Error, "text cell rejected");
console.log("ok");
