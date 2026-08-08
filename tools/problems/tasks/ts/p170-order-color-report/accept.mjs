import assert from "node:assert/strict";
import { orderColorReport } from "./solution.ts";

const path = [[1], [0, 2], [1, 3], [2]];
const ring = [
  [1, 4],
  [0, 2],
  [1, 3],
  [2, 4],
  [0, 3],
];
const star = [[1, 2, 3], [0], [0], [0]];
const triangle = [
  [1, 2],
  [0, 2],
  [0, 1],
];

assert.deepEqual(
  orderColorReport(path, [0, 1, 2, 3]),
  [
    [0, 1, 0, 1],
    [2],
  ],
  "a chain alternates",
);
assert.deepEqual(
  orderColorReport(path, [1, 2, 0, 3]),
  [
    [1, 0, 1, 0],
    [2],
  ],
  "starting in the middle flips the pattern",
);
assert.deepEqual(
  orderColorReport(path, [0, 3, 1, 2]),
  [
    [0, 1, 2, 0],
    [3],
  ],
  "an awkward sequence costs a third channel",
);
assert.deepEqual(
  orderColorReport(triangle, [0, 1, 2]),
  [
    [0, 1, 2],
    [3],
  ],
  "every transmitter clashes with every other",
);
assert.deepEqual(
  orderColorReport(star, [1, 2, 3, 0]),
  [
    [1, 0, 0, 0],
    [2],
  ],
  "the hub goes last",
);
assert.deepEqual(
  orderColorReport(star, [0, 1, 2, 3]),
  [
    [0, 1, 1, 1],
    [2],
  ],
  "the hub goes first",
);
assert.deepEqual(
  orderColorReport(ring, [0, 1, 2, 3, 4]),
  [
    [0, 1, 0, 1, 2],
    [3],
  ],
  "an odd ring needs three",
);
assert.deepEqual(
  orderColorReport([[], [], []], [2, 0, 1]),
  [
    [0, 0, 0],
    [1],
  ],
  "no clashes at all",
);
assert.deepEqual(orderColorReport([[]], [0]), [[0], [1]], "a lone transmitter");

assert.throws(() => orderColorReport([], []), Error, "no transmitters rejected");
assert.throws(
  () => orderColorReport([[1], [0]], [0, 5]),
  Error,
  "sequence names a stranger",
);
assert.throws(
  () => orderColorReport([[1], [0]], [0, 0]),
  Error,
  "sequence repeats a transmitter",
);
assert.throws(
  () => orderColorReport([[1], [0]], [0]),
  Error,
  "sequence too short rejected",
);
assert.throws(
  () => orderColorReport([[0], [0]], [0, 1]),
  Error,
  "self clash rejected",
);
assert.throws(
  () => orderColorReport([[1], []], [0, 1]),
  Error,
  "one-sided clash rejected",
);
assert.throws(
  () => orderColorReport([[2], [0]], [0, 1]),
  Error,
  "clash with a stranger rejected",
);
console.log("ok");
