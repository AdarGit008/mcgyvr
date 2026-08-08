import assert from "node:assert/strict";
import { tripletChainCells } from "./solution.ts";

assert.deepEqual(
  tripletChainCells(
    [
      [0, 0, 2],
      [0, 1, 3],
      [1, 2, 4],
    ],
    [
      [0, 1, 5],
      [1, 1, 7],
      [2, 0, 6],
    ],
    2,
    3,
    2,
  ),
  [
    [0, 1, 31],
    [1, 0, 24],
  ],
  "routes through several middles add, and the source orders ahead of the sink",
);

assert.deepEqual(
  tripletChainCells(
    [
      [0, 0, 2],
      [0, 1, 3],
    ],
    [
      [0, 0, 3],
      [1, 0, -2],
    ],
    1,
    2,
    1,
  ),
  [],
  "a pair whose routes cancel is dropped",
);

assert.deepEqual(
  tripletChainCells([[0, 0, 5]], [], 1, 1, 1),
  [],
  "an empty second bag leaves no route at all",
);

assert.deepEqual(
  tripletChainCells([], [[0, 0, 5]], 1, 1, 1),
  [],
  "an empty first bag leaves no route at all",
);

assert.deepEqual(
  tripletChainCells([[0, 1, 6]], [[0, 0, 9]], 1, 2, 1),
  [],
  "a middle nothing leaves from yields no route, and the join is on the middle",
);

assert.deepEqual(
  tripletChainCells(
    [
      [2, 0, 1],
      [0, 0, 1],
      [1, 0, 1],
    ],
    [
      [0, 2, 1],
      [0, 0, 1],
    ],
    3,
    1,
    3,
  ),
  [
    [0, 0, 1],
    [0, 2, 1],
    [1, 0, 1],
    [1, 2, 1],
    [2, 0, 1],
    [2, 2, 1],
  ],
  "a full cross product comes back in source-then-sink order",
);

assert.deepEqual(
  tripletChainCells([[0, 0, -10000]], [[0, 0, 10000]], 1, 1, 1),
  [[0, 0, -100000000]],
  "the weight limit multiplies out exactly",
);

assert.throws(
  () => tripletChainCells([[0, 3, 1]], [], 1, 3, 1),
  Error,
  "a middle at the edge of its band is rejected",
);
assert.throws(
  () => tripletChainCells([[0, 0, 1]], [[-1, 0, 1]], 1, 1, 1),
  Error,
  "a negative endpoint is rejected",
);
assert.throws(
  () => tripletChainCells([[0, 0, 0]], [], 1, 1, 1),
  Error,
  "a stored weight of nothing is rejected",
);
assert.throws(
  () =>
    tripletChainCells(
      [
        [0, 0, 1],
        [0, 0, 2],
      ],
      [],
      1,
      1,
      1,
    ),
  Error,
  "one bag holding the same endpoints twice is rejected",
);
assert.throws(
  () => tripletChainCells([[0, 0, 10001]], [], 1, 1, 1),
  Error,
  "a weight past the size limit is rejected",
);
assert.throws(
  () => tripletChainCells([[0, 0, 1]], [], 1, 0, 1),
  Error,
  "a band width of nothing is rejected",
);
assert.throws(
  () => tripletChainCells([[0, 0]], [], 1, 1, 1),
  Error,
  "a link that is not a triple is rejected",
);
assert.throws(
  () => tripletChainCells("bag", [], 1, 1, 1),
  Error,
  "a bag that is not a list is rejected",
);
console.log("ok");
