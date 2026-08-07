import assert from "node:assert/strict";
import { latticeInverse } from "./solution.ts";

// Negative zero and zero are the same whole number; the comparison should not
// care which one an arithmetic route happened to produce.
function undo(frame) {
  const rows = latticeInverse(frame);
  return rows.map((row) => row.map((entry) => (entry === 0 ? 0 : entry)));
}

assert.deepEqual(
  undo([
    [1, 2],
    [0, 1],
  ]),
  [
    [1, -2],
    [0, 1],
  ],
  "a shear undoes by shearing back",
);
assert.deepEqual(
  undo([
    [2, 3],
    [1, 2],
  ]),
  [
    [2, -3],
    [-1, 2],
  ],
  "determinant one",
);
assert.deepEqual(
  undo([
    [0, -1],
    [1, 0],
  ]),
  [
    [0, 1],
    [-1, 0],
  ],
  "a quarter turn",
);
assert.deepEqual(
  undo([
    [3, 4],
    [5, 7],
  ]),
  [
    [7, -4],
    [-5, 3],
  ],
  "larger entries",
);
assert.deepEqual(
  undo([
    [1, 1],
    [2, 1],
  ]),
  [
    [-1, 1],
    [2, -1],
  ],
  "determinant minus one",
);
assert.deepEqual(
  undo([
    [1, 2],
    [3, 4],
  ]),
  [],
  "determinant minus two cannot be undone",
);
assert.deepEqual(
  undo([
    [2, 4],
    [1, 2],
  ]),
  [],
  "a flat frame cannot be undone",
);
assert.deepEqual(
  undo([
    [1, 2, 3],
    [0, 1, 4],
    [0, 0, 1],
  ]),
  [
    [1, -2, 5],
    [0, 1, -4],
    [0, 0, 1],
  ],
  "three rows, upper corner clear",
);
assert.deepEqual(
  undo([
    [0, 0, 1],
    [1, 0, 0],
    [0, 1, 0],
  ]),
  [
    [0, 1, 0],
    [0, 0, 1],
    [1, 0, 0],
  ],
  "a three-way shuffle undoes by shuffling the other way",
);
assert.deepEqual(
  undo([
    [2, 3, 1],
    [1, 2, 1],
    [1, 1, 1],
  ]),
  [
    [1, -2, 1],
    [0, 1, -1],
    [-1, 1, 1],
  ],
  "three rows, dense",
);
assert.deepEqual(
  undo([
    [0, 1, 4],
    [1, 2, 3],
    [0, 0, 1],
  ]),
  [
    [-2, 1, 5],
    [1, 0, -4],
    [0, 0, 1],
  ],
  "three rows, determinant minus one",
);
assert.deepEqual(
  undo([
    [2, 0, 0],
    [0, 1, 0],
    [0, 0, 1],
  ]),
  [],
  "determinant two cannot be undone",
);
assert.deepEqual(
  undo([
    [1, 2, 3],
    [4, 5, 6],
    [7, 8, 9],
  ]),
  [],
  "three flat rows cannot be undone",
);

assert.throws(() => latticeInverse([[1]]), Error, "one row rejected");
assert.throws(() => latticeInverse("f"), Error, "non-list rejected");
assert.throws(() => latticeInverse([[1, 2], [3]]), Error, "ragged rows rejected");
assert.throws(
  () =>
    latticeInverse([
      [1, 0, 0, 0],
      [0, 1, 0, 0],
      [0, 0, 1, 0],
      [0, 0, 0, 1],
    ]),
  Error,
  "four rows rejected",
);
assert.throws(
  () => latticeInverse([[1, 0.5], [0, 1]]),
  Error,
  "fractional entry rejected",
);
console.log("ok");
