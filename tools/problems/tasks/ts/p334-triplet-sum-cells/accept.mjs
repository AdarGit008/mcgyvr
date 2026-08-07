import assert from "node:assert/strict";
import { tripletSumCells } from "./solution.ts";

assert.deepEqual(
  tripletSumCells(
    [
      [0, 0, 1],
      [1, 2, 3],
    ],
    [
      [0, 0, 4],
      [2, 1, -5],
    ],
    3,
    3,
  ),
  [
    [0, 0, 5],
    [1, 2, 3],
    [2, 1, -5],
  ],
  "shared cells add, lone cells carry through",
);

assert.deepEqual(
  tripletSumCells([[0, 0, 7]], [[0, 0, -7]], 2, 2),
  [],
  "a cell that cancels is left out",
);

assert.deepEqual(
  tripletSumCells([], [], 4, 4),
  [],
  "two bare sheets overlay to nothing",
);

assert.deepEqual(
  tripletSumCells(
    [],
    [
      [2, 0, 9],
      [0, 3, 8],
    ],
    3,
    4,
  ),
  [
    [0, 3, 8],
    [2, 0, 9],
  ],
  "a bare sheet leaves the other one, reordered",
);

assert.deepEqual(
  tripletSumCells(
    [
      [1, 1, 2],
      [0, 5, 1],
      [1, 0, 4],
    ],
    [
      [1, 1, -2],
      [0, 5, 6],
    ],
    2,
    6,
  ),
  [
    [0, 5, 7],
    [1, 0, 4],
  ],
  "row order beats column order and the cancelled cell drops",
);

assert.deepEqual(
  tripletSumCells([[9999, 9999, 1000000000]], [[9999, 9999, -1]], 10000, 10000),
  [[9999, 9999, 999999999]],
  "the far corner and the mark limit both hold",
);

assert.throws(
  () => tripletSumCells([[0, 0, 1]], [[0, 0, 1]], 0, 3),
  Error,
  "a shape with no rows is rejected",
);
assert.throws(
  () => tripletSumCells([[3, 0, 1]], [], 3, 3),
  Error,
  "a row index at the edge of the shape is rejected",
);
assert.throws(
  () => tripletSumCells([[0, -1, 1]], [], 3, 3),
  Error,
  "a negative column index is rejected",
);
assert.throws(
  () => tripletSumCells([[0, 0, 0]], [], 3, 3),
  Error,
  "a stored mark of nothing is rejected",
);
assert.throws(
  () =>
    tripletSumCells(
      [
        [1, 1, 2],
        [1, 1, 3],
      ],
      [],
      3,
      3,
    ),
  Error,
  "one sheet naming a cell twice is rejected",
);
assert.throws(
  () => tripletSumCells([[0, 0, 1.5]], [], 3, 3),
  Error,
  "a fractional mark is rejected",
);
assert.throws(
  () => tripletSumCells([[0, 0, 1000000001]], [], 3, 3),
  Error,
  "a mark past the limit is rejected",
);
assert.throws(
  () => tripletSumCells([[0, 0]], [], 3, 3),
  Error,
  "an entry that is not a triple is rejected",
);
assert.throws(
  () => tripletSumCells("sheet", [], 3, 3),
  Error,
  "a non-list sheet is rejected",
);
console.log("ok");
