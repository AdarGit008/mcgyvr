import assert from "node:assert/strict";
import { countPieceTours } from "./solution.ts";

assert.equal(
  countPieceTours(1, 1, [0, 0], []),
  1,
  "a board of one square is already toured",
);
assert.equal(
  countPieceTours(3, 1, [0, 0], []),
  1,
  "a single row admits only the walk to its far end",
);
assert.equal(
  countPieceTours(2, 2, [0, 0], []),
  2,
  "the four corners of a small board, two ways round",
);
assert.equal(
  countPieceTours(2, 2, [0, 0], [[1, 1]]),
  0,
  "blocking a corner strands the two squares beside it",
);
assert.equal(
  countPieceTours(2, 3, [0, 0], []),
  3,
  "two columns of three rows",
);
assert.equal(
  countPieceTours(3, 3, [0, 0], []),
  22,
  "a nine-square board started at a corner",
);
assert.equal(
  countPieceTours(3, 3, [1, 1], []),
  16,
  "the same board started at its middle",
);
assert.equal(
  countPieceTours(3, 3, [0, 0], [[1, 1]]),
  2,
  "blocking the middle leaves only a rim to walk",
);
assert.equal(
  countPieceTours(3, 3, [0, 0], [
    [0, 1],
    [1, 0],
  ]),
  4,
  "walling in the start square forces the opening leap",
);
assert.equal(
  countPieceTours(3, 4, [0, 0], []),
  194,
  "the widest board the rules allow",
);
assert.equal(
  countPieceTours(4, 4, [0, 0], [
    [0, 3],
    [1, 3],
    [2, 3],
    [3, 3],
  ]),
  194,
  "blocking a whole column reproduces the narrower board",
);

assert.throws(() => countPieceTours(0, 2, [0, 0], []), Error, "a board with no columns");
assert.throws(
  () => countPieceTours(2, 2.5, [0, 0], []),
  Error,
  "a fractional row count",
);
assert.throws(() => countPieceTours(4, 4, [0, 0], []), Error, "too many open squares");
assert.throws(() => countPieceTours(2, 2, [0, 2], []), Error, "start off the board");
assert.throws(
  () => countPieceTours(2, 2, [0, 0], [[0, 0]]),
  Error,
  "start on a blocked square",
);
assert.throws(
  () => countPieceTours(2, 2, [0, 0], [[0, 5]]),
  Error,
  "a blocked square off the board",
);
assert.throws(
  () =>
    countPieceTours(2, 2, [0, 0], [
      [0, 1],
      [0, 1],
    ]),
  Error,
  "the same square blocked twice",
);
assert.throws(() => countPieceTours(2, 2, [0, 0], "x"), Error, "blocked is not a list");
assert.throws(() => countPieceTours(2, 2, [0], []), Error, "start is not a pair");
console.log("ok");
