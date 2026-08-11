import assert from "node:assert/strict";
import { planBatches } from "./solution.ts";

assert.deepEqual(
  planBatches(4, 10),
  { loads: [4], splits: 0, rounds: 0 },
  "a consignment within capacity ships whole",
);
assert.deepEqual(
  planBatches(7, 7),
  { loads: [7], splits: 0, rounds: 0 },
  "a consignment exactly at capacity ships whole",
);
assert.deepEqual(
  planBatches(10, 5),
  { loads: [5, 5], splits: 1, rounds: 1 },
  "one even split",
);
assert.deepEqual(
  planBatches(9, 5),
  { loads: [5, 4], splits: 1, rounds: 1 },
  "an odd split puts the larger half first",
);
assert.deepEqual(
  planBatches(10, 3),
  { loads: [3, 2, 3, 2], splits: 3, rounds: 2 },
  "both halves split again",
);
assert.deepEqual(
  planBatches(9, 2),
  { loads: [2, 1, 2, 2, 2], splits: 4, rounds: 3 },
  "an uneven tree splits deeper on one side",
);
assert.deepEqual(
  planBatches(3, 1),
  { loads: [1, 1, 1], splits: 2, rounds: 2 },
  "capacity one reduces to single-parcel loads",
);
assert.throws(() => planBatches(0, 5), Error, "zero units is rejected");
assert.throws(() => planBatches(6, 2.5), Error, "a fractional capacity is rejected");
console.log("ok");
