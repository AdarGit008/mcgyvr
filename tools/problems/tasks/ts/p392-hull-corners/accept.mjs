import assert from "node:assert/strict";
import { hullCorners } from "./solution.ts";

assert.deepEqual(
  hullCorners([
    [0, 0],
    [2, 0],
    [2, 2],
    [0, 2],
  ]),
  [
    [0, 0],
    [2, 0],
    [2, 2],
    [0, 2],
  ],
  "a square keeps its four posts, counter-clockwise from the least corner",
);

assert.deepEqual(
  hullCorners([
    [1, 0],
    [0, 2],
    [2, 2],
    [1, 1],
    [0, 0],
    [2, 0],
  ]),
  [
    [0, 0],
    [2, 0],
    [2, 2],
    [0, 2],
  ],
  "a post flat on a run and a marker inside are both left out",
);

assert.deepEqual(
  hullCorners([
    [-2, -2],
    [2, -2],
    [2, 2],
    [-2, 2],
    [0, 0],
    [-2, -2],
  ]),
  [
    [-2, -2],
    [2, -2],
    [2, 2],
    [-2, 2],
  ],
  "negative coordinates and a repeat change nothing",
);

assert.deepEqual(
  hullCorners([
    [0, 0],
    [4, 0],
    [0, 3],
  ]),
  [
    [0, 0],
    [4, 0],
    [0, 3],
  ],
  "a triangle already given counter-clockwise",
);

assert.deepEqual(
  hullCorners([
    [0, 3],
    [4, 0],
    [0, 0],
  ]),
  [
    [0, 0],
    [4, 0],
    [0, 3],
  ],
  "the same triangle given the other way round",
);

assert.deepEqual(
  hullCorners([
    [3, 3],
    [3, 3],
    [3, 3],
  ]),
  [[3, 3]],
  "one shared spot collapses to that spot",
);

assert.deepEqual(
  hullCorners([
    [2, 4],
    [-1, -2],
    [1, 2],
    [0, 0],
  ]),
  [
    [-1, -2],
    [2, 4],
  ],
  "a straight run collapses to its two far ends",
);

assert.deepEqual(hullCorners([[7, -5]]), [[7, -5]], "one marker is one post");

assert.deepEqual(
  hullCorners([
    [0, 0],
    [0, 5],
    [0, 2],
  ]),
  [
    [0, 0],
    [0, 5],
  ],
  "a vertical run keeps only its ends",
);

assert.throws(() => hullCorners([]), Error, "an empty list is rejected");
assert.throws(() => hullCorners("points"), Error, "a non-list is rejected");
assert.throws(
  () => hullCorners([[1, 2, 3]]),
  Error,
  "a triple is not a marker",
);
assert.throws(
  () => hullCorners([[1, 1.5]]),
  Error,
  "a fractional coordinate is rejected",
);
assert.throws(
  () => hullCorners([[0, 0], [2000000, 1]]),
  Error,
  "an oversized coordinate is rejected",
);
console.log("ok");
