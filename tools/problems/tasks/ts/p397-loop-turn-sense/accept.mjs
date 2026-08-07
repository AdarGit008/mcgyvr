import assert from "node:assert/strict";
import { loopTurnSense } from "./solution.ts";

assert.deepEqual(
  loopTurnSense([
    [1, 1],
    [5, 2],
    [2, 6],
  ]),
  { doubled: 19, sense: "counter" },
  "a slanted triangle whose closing side carries weight",
);

assert.deepEqual(
  loopTurnSense([
    [2, 6],
    [5, 2],
    [1, 1],
  ]),
  { doubled: 19, sense: "clockwise" },
  "the same triangle listed backwards keeps the ground and flips the word",
);

assert.deepEqual(
  loopTurnSense([
    [0, 0],
    [4, 0],
    [0, 3],
  ]),
  { doubled: 12, sense: "counter" },
  "a right triangle listed anticlockwise",
);

assert.deepEqual(
  loopTurnSense([
    [0, 0],
    [0, 3],
    [4, 0],
  ]),
  { doubled: 12, sense: "clockwise" },
  "the same right triangle listed the other way about",
);

assert.deepEqual(
  loopTurnSense([
    [0, 0],
    [4, 0],
    [4, 4],
    [0, 4],
  ]),
  { doubled: 32, sense: "counter" },
  "a four-wide square",
);

assert.deepEqual(
  loopTurnSense([
    [-1, -1],
    [3, -1],
    [3, 2],
    [-1, 2],
  ]),
  { doubled: 24, sense: "counter" },
  "negative measures pen in ground all the same",
);

assert.deepEqual(
  loopTurnSense([
    [0, 0],
    [2, 0],
    [5, 0],
  ]),
  { doubled: 0, sense: "flat" },
  "studs strung along one line pen in nothing",
);

assert.deepEqual(
  loopTurnSense([
    [3, 3],
    [1, 2],
    [-1, 1],
  ]),
  { doubled: 0, sense: "flat" },
  "a slanted line of studs is flat too",
);

assert.throws(
  () => loopTurnSense([[0, 0], [1, 1]]),
  Error,
  "two studs are not a loop",
);
assert.throws(() => loopTurnSense("loop"), Error, "a non-list is rejected");
assert.throws(
  () => loopTurnSense([[0, 0], [2, 0], [0, 0]]),
  Error,
  "a repeated stud is rejected",
);
assert.throws(
  () => loopTurnSense([[0, 0], [2, 0], [1, 2.5]]),
  Error,
  "a fractional measure is rejected",
);
assert.throws(
  () => loopTurnSense([[0, 0], [20001, 0], [0, 2]]),
  Error,
  "an oversized measure is rejected",
);
console.log("ok");
