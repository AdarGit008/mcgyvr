import assert from "node:assert/strict";
import { siftDownRun } from "./solution.ts";

assert.deepEqual(
  siftDownRun([9, 2, 4, 5, 3, 7, 6], 0),
  [
    [2, 3, 4, 5, 9, 7, 6],
    [0, 1, 4],
  ],
  "sinks two levels",
);
assert.deepEqual(siftDownRun([1, 2, 3], 0), [[1, 2, 3], [0]], "already settled");
assert.deepEqual(siftDownRun([5, 3, 3], 0), [[3, 5, 3], [0, 1]], "tie takes the left");
assert.deepEqual(
  siftDownRun([8, 9, 1, 10, 11], 0),
  [
    [1, 9, 8, 10, 11],
    [0, 2],
  ],
  "smaller right child wins",
);
assert.deepEqual(siftDownRun([1, 4, 3, 7], 3), [[1, 4, 3, 7], [3]], "leaf start");
assert.deepEqual(
  siftDownRun([0, 9, 2, 3, 4, 5, 6, 7, 8], 1),
  [
    [0, 3, 2, 7, 4, 5, 6, 9, 8],
    [1, 3, 7],
  ],
  "start below the root",
);
assert.deepEqual(siftDownRun([5, 1], 0), [[1, 5], [0, 1]], "only a left child");
assert.deepEqual(
  siftDownRun([3, -1, -2], 0),
  [
    [-2, -1, 3],
    [0, 2],
  ],
  "negatives",
);
assert.deepEqual(siftDownRun([7], 0), [[7], [0]], "lone slot");

const caller = [9, 2, 4];
siftDownRun(caller, 0);
assert.deepEqual(caller, [9, 2, 4], "caller's array untouched");

assert.throws(() => siftDownRun([], 0), Error, "empty array rejected");
assert.throws(() => siftDownRun([1, 2], -1), Error, "negative start rejected");
assert.throws(() => siftDownRun([1, 2], 2), Error, "start past the end rejected");
assert.throws(() => siftDownRun([1, 2.5], 0), Error, "fraction entry rejected");
assert.throws(() => siftDownRun([1, 2], 0.5), Error, "fractional start rejected");
console.log("ok");
