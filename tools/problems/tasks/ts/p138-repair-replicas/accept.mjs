import assert from "node:assert/strict";
import { repairReplicas } from "./solution.ts";

assert.deepEqual(
  repairReplicas([
    [1, 2],
    [1, 2],
    [1, 3],
  ]),
  [1, 2],
  "two of three agree at each position",
);
assert.deepEqual(
  repairReplicas([
    [1, null],
    [1, 5],
    [2, 5],
  ]),
  [1, 5],
  "a lost slot shrinks the denominator, so 2 of 2 survivors is a majority",
);
assert.deepEqual(
  repairReplicas([
    [4, 9],
    [null, 9],
    [4, 9],
  ]),
  [4, 9],
  "survivors can agree unanimously around a hole",
);
assert.deepEqual(repairReplicas([[7, 8]]), [7, 8], "one replica is its own majority");
assert.deepEqual(repairReplicas([[], [], []]), [], "empty replicas rebuild to empty");
assert.throws(
  () =>
    repairReplicas([
      [1],
      [2],
    ]),
  Error,
  "a one-against-one split has no strict majority",
);
assert.throws(
  () =>
    repairReplicas([
      [1, null],
      [1, null],
    ]),
  Error,
  "a position lost everywhere is unrecoverable",
);
assert.throws(() => repairReplicas([]), Error, "an empty replica list is rejected");
assert.throws(
  () =>
    repairReplicas([
      [1, 2],
      [1],
    ]),
  Error,
  "ragged replica lengths are rejected",
);
assert.throws(
  () => repairReplicas([["x"], ["x"]]),
  Error,
  "a non-integer slot is rejected",
);
assert.throws(
  () =>
    repairReplicas([
      [1, 1],
      [2, 1],
      [2, 1],
      [3, 1],
    ]),
  Error,
  "a mere plurality of 2 in 4 is not a strict majority",
);
console.log("ok");
