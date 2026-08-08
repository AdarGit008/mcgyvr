import assert from "node:assert/strict";
import { segmentRelation } from "./solution.ts";

assert.equal(
  segmentRelation(
    [
      [0, 0],
      [4, 4],
    ],
    [
      [0, 4],
      [4, 0],
    ],
  ),
  "pinned",
  "a crossing on a graph-paper corner",
);

assert.equal(
  segmentRelation(
    [
      [0, 0],
      [2, 1],
    ],
    [
      [0, 1],
      [2, 0],
    ],
  ),
  "adrift",
  "a meeting halfway up a square is between crossings",
);

assert.equal(
  segmentRelation(
    [
      [0, 0],
      [3, 3],
    ],
    [
      [0, 1],
      [3, 0],
    ],
  ),
  "adrift",
  "three quarters along is between crossings too",
);

assert.equal(
  segmentRelation(
    [
      [0, 0],
      [4, 0],
    ],
    [
      [2, 0],
      [2, 5],
    ],
  ),
  "pinned",
  "a tip planted on the middle of the other rod",
);

assert.equal(
  segmentRelation(
    [
      [0, 0],
      [2, 0],
    ],
    [
      [0, 3],
      [2, 3],
    ],
  ),
  "clear",
  "rods that never converge",
);

assert.equal(
  segmentRelation(
    [
      [0, 0],
      [1, 0],
    ],
    [
      [3, -2],
      [3, 2],
    ],
  ),
  "clear",
  "the lines would converge past the ends of the rods",
);

assert.equal(
  segmentRelation(
    [
      [-4, -2],
      [4, 2],
    ],
    [
      [0, 0],
      [8, 4],
    ],
  ),
  "shared",
  "a common length along one line",
);

assert.equal(
  segmentRelation(
    [
      [0, 0],
      [2, 2],
    ],
    [
      [2, 2],
      [7, 7],
    ],
  ),
  "pinned",
  "same line, meeting at one tip only",
);

assert.equal(
  segmentRelation(
    [
      [0, 0],
      [1, 1],
    ],
    [
      [4, 4],
      [6, 6],
    ],
  ),
  "clear",
  "same line but a gap between the rods",
);

assert.equal(
  segmentRelation(
    [
      [-3, -3],
      [-1, -1],
    ],
    [
      [-3, -1],
      [-1, -3],
    ],
  ),
  "pinned",
  "negative measures cross on a corner",
);

assert.throws(
  () => segmentRelation([[0, 0]], [[0, 1], [1, 0]]),
  Error,
  "one tip is not a rod",
);
assert.throws(
  () => segmentRelation([[3, 3], [3, 3]], [[0, 1], [1, 0]]),
  Error,
  "coincident tips are rejected",
);
assert.throws(
  () => segmentRelation([[0, 0], [1, null]], [[0, 1], [1, 0]]),
  Error,
  "a missing measure is rejected",
);
assert.throws(
  () => segmentRelation([[0, 0], [501, 0]], [[0, 1], [1, 0]]),
  Error,
  "an oversized measure is rejected",
);
assert.throws(
  () => segmentRelation(null, [[0, 1], [1, 0]]),
  Error,
  "a missing rod is rejected",
);
console.log("ok");
