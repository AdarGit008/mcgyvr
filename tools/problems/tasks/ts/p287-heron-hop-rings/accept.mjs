import assert from "node:assert/strict";
import { reachByHops } from "./solution.ts";

assert.deepEqual(
  reachByHops(1, 1, [0, 0], [], 0),
  [1],
  "no hops at all still counts the standing square",
);
assert.deepEqual(
  reachByHops(1, 1, [0, 0], [], 3),
  [1, 0, 0, 0],
  "a fen of one square leaves every later ring empty",
);
assert.deepEqual(
  reachByHops(5, 5, [0, 0], [], 1),
  [1, 4],
  "a corner offers a short and a long hop each way",
);
assert.deepEqual(
  reachByHops(5, 5, [0, 0], [], 2),
  [1, 4, 8],
  "the second ring off the corner",
);
assert.deepEqual(
  reachByHops(3, 3, [1, 1], [], 2),
  [1, 4, 4],
  "a small fen fills in two rings",
);
assert.deepEqual(
  reachByHops(6, 1, [0, 0], [], 2),
  [1, 2, 2],
  "one row deep, hopping along the line",
);
assert.deepEqual(
  reachByHops(4, 4, [3, 3], [], 3),
  [1, 4, 6, 4],
  "starting at the far corner needs the hop back toward the top",
);
assert.deepEqual(
  reachByHops(
    4,
    4,
    [0, 0],
    [
      [0, 1],
      [1, 0],
    ],
    1,
  ),
  [1, 2],
  "marsh beside the start closes both short hops",
);
assert.deepEqual(
  reachByHops(
    4,
    4,
    [0, 0],
    [
      [0, 1],
      [1, 0],
    ],
    2,
  ),
  [1, 2, 5],
  "the fen still opens up once the long hops are taken",
);

assert.throws(() => reachByHops(0, 3, [0, 0], [], 1), Error, "a fen with no columns");
assert.throws(
  () => reachByHops(3, 2.5, [0, 0], [], 1),
  Error,
  "a fractional depth",
);
assert.throws(() => reachByHops(3, 3, [0, 0], [], -1), Error, "a negative hop budget");
assert.throws(() => reachByHops(3, 3, [0, 3], [], 1), Error, "start off the fen");
assert.throws(
  () => reachByHops(3, 3, [0, 0], [[0, 0]], 1),
  Error,
  "start standing in marsh",
);
assert.throws(
  () => reachByHops(3, 3, [0, 0], [[9, 0]], 1),
  Error,
  "marsh off the fen",
);
assert.throws(
  () =>
    reachByHops(
      3,
      3,
      [0, 0],
      [
        [1, 1],
        [1, 1],
      ],
      1,
    ),
  Error,
  "the same marsh square twice",
);
assert.throws(() => reachByHops(3, 3, [0, 0], "wet", 1), Error, "marsh is not a list");
assert.throws(() => reachByHops(3, 3, [0], [], 1), Error, "start is not a pair");
console.log("ok");
