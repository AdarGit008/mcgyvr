import assert from "node:assert/strict";
import { mendShards } from "./solution.ts";

assert.deepEqual(
  mendShards([
    [1, 2],
    [1, 2],
    [3, 2],
  ]),
  [1, 2],
  "the most-held value wins each position",
);
assert.deepEqual(
  mendShards([
    [null, 5],
    [7, null],
    [7, 5],
  ]),
  [7, 5],
  "corrupted slots simply drop out of the count",
);
assert.deepEqual(
  mendShards([
    [null, 1],
    [null, 1],
    [4, null],
  ]),
  [4, 1],
  "corruption is never a candidate, even when it is the most common state",
);
assert.deepEqual(
  mendShards([[2], [9], [9], [2]]),
  [2],
  "a count tie goes to the value held by the earliest copy",
);
assert.deepEqual(
  mendShards([[9], [2], [2], [9]]),
  [9],
  "the earliest-copy rule is about position in the list, not value size",
);
assert.deepEqual(
  mendShards([[null], [null]]),
  [-1],
  "a position corrupted everywhere mends to -1",
);
assert.deepEqual(
  mendShards([[5, null, 3]]),
  [5, -1, 3],
  "a single copy mends to itself with -1 in its holes",
);
assert.deepEqual(mendShards([[], []]), [], "empty copies mend to an empty array");
assert.throws(
  () =>
    mendShards([
      [1, 2],
      [1],
    ]),
  Error,
  "copies of different lengths are rejected",
);
assert.throws(() => mendShards([[-3]]), Error, "a negative slot is rejected");
assert.throws(() => mendShards([["a"]]), Error, "a string slot is rejected");
assert.throws(() => mendShards([]), Error, "an empty list of copies is rejected");
console.log("ok");
