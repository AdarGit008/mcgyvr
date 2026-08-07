import assert from "node:assert/strict";
import { hullEdgeStops } from "./solution.ts";

assert.equal(
  hullEdgeStops([
    [0, 0],
    [1, 0],
    [1, 1],
    [0, 1],
  ]),
  4,
  "the unit square touches its four turning posts and nothing else",
);

assert.equal(
  hullEdgeStops([
    [0, 0],
    [2, 0],
    [2, 2],
    [0, 2],
    [1, 1],
  ]),
  8,
  "a two-wide square touches eight, and the peg inside is ignored",
);

assert.equal(
  hullEdgeStops([
    [0, 0],
    [4, 0],
    [0, 3],
  ]),
  8,
  "the 4 by 3 triangle: four along the base, three up the side, one on the slant",
);

assert.equal(
  hullEdgeStops([
    [-3, -3],
    [3, -3],
    [3, 3],
    [-3, 3],
  ]),
  24,
  "a six-wide square around the origin",
);

assert.equal(
  hullEdgeStops([
    [0, 0],
    [3, 0],
    [1, 0],
  ]),
  4,
  "a flat run is walked once, not twice",
);

assert.equal(
  hullEdgeStops([
    [0, 0],
    [4, 6],
  ]),
  3,
  "a slanted run stops only where the run meets the grid",
);

assert.equal(
  hullEdgeStops([
    [5, -2],
    [5, -2],
  ]),
  1,
  "one spot touches exactly one grid point",
);

assert.equal(hullEdgeStops([[0, 0]]), 1, "a lone peg touches one");

assert.throws(() => hullEdgeStops([]), Error, "an empty list is rejected");
assert.throws(() => hullEdgeStops(17), Error, "a non-list is rejected");
assert.throws(() => hullEdgeStops([[1]]), Error, "a single number is not a peg");
assert.throws(
  () => hullEdgeStops([[0, 0], ["2", 2]]),
  Error,
  "a text coordinate is rejected",
);
assert.throws(
  () => hullEdgeStops([[0, 0], [1, 1000001]]),
  Error,
  "an oversized coordinate is rejected",
);
console.log("ok");
