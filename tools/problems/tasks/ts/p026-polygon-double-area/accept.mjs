import assert from "node:assert/strict";
import { polygonDoubleArea } from "./solution.ts";

assert.equal(polygonDoubleArea([[0, 0], [1, 0], [1, 1], [0, 1]]), 2, "unit square");
assert.equal(polygonDoubleArea([[0, 0], [4, 0], [0, 3]]), 12, "right triangle");
assert.equal(polygonDoubleArea([[0, 0], [0, 1], [1, 1], [1, 0]]), 2, "clockwise matches");
assert.equal(
  polygonDoubleArea([[0, 0], [4, 0], [4, 4], [2, 2], [0, 4]]),
  24,
  "concave notch",
);
assert.equal(
  polygonDoubleArea([[10, 10], [11, 10], [11, 11], [10, 11]]),
  2,
  "translation does not change area",
);
assert.equal(polygonDoubleArea([[-1, -1], [1, -1], [1, 1], [-1, 1]]), 8, "negative coords");
assert.equal(polygonDoubleArea([[0, 0], [2, 0], [4, 1]]), 2, "thin sliver triangle");
assert.equal(polygonDoubleArea([[0, 0], [2, 0], [4, 0]]), 0, "collinear encloses nothing");
assert.throws(() => polygonDoubleArea([[0, 0], [1, 1]]), Error, "two vertices rejected");
assert.throws(
  () => polygonDoubleArea([[0, 0], [0, 0], [1, 1]]),
  Error,
  "repeated consecutive vertex rejected",
);
assert.throws(
  () => polygonDoubleArea([[0, 0], [1, 0], [1, 1], [0, 0]]),
  Error,
  "closed ring input rejected",
);
assert.throws(
  () => polygonDoubleArea([[0, 0], [1.5, 0], [1, 1]]),
  Error,
  "fractional coordinate rejected",
);
assert.throws(() => polygonDoubleArea([[0, 0], [1], [1, 1]]), Error, "short pair rejected");
console.log("ok");
