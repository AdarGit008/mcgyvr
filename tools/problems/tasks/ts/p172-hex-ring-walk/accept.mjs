import assert from "node:assert/strict";
import { hexRingWalk } from "./solution.ts";

assert.deepEqual(
  hexRingWalk([0, 0], 1),
  [
    [-1, 1],
    [0, 1],
    [1, 0],
    [1, -1],
    [0, -1],
    [-1, 0],
  ],
  "radius one opens southwest of the centre and runs east first",
);
assert.deepEqual(hexRingWalk([3, -2], 0), [[3, -2]], "radius zero is the centre alone");
assert.deepEqual(
  hexRingWalk([2, -1], 1),
  [
    [1, 0],
    [2, 0],
    [3, -1],
    [3, -2],
    [2, -2],
    [1, -1],
  ],
  "the walk translates with the centre",
);
assert.deepEqual(
  hexRingWalk([0, 0], 2),
  [
    [-2, 2],
    [-1, 2],
    [0, 2],
    [1, 1],
    [2, 0],
    [2, -1],
    [2, -2],
    [1, -2],
    [0, -2],
    [-1, -1],
    [-2, 0],
    [-2, 1],
  ],
  "radius two visits twelve cells, two per direction",
);

const wide = hexRingWalk([0, 0], 3);
assert.equal(wide.length, 18, "a ring of radius three holds eighteen cells");
assert.deepEqual(wide[0], [-3, 3], "the walk opens three southwest steps out");
assert.deepEqual(wide[17], [-3, 2], "the final cell neighbours the opening cell");
assert.equal(
  new Set(wide.map((cell) => cell.join(","))).size,
  18,
  "no cell is recorded twice",
);
const far = wide.every(
  (cell) =>
    (Math.abs(cell[0]) + Math.abs(cell[1]) + Math.abs(cell[0] + cell[1])) / 2 === 3,
);
assert.ok(far, "every recorded cell stands three steps from the centre");

const off = hexRingWalk([-4, 7], 2);
assert.deepEqual(off[0], [-6, 9], "a far centre still opens southwest");
assert.equal(off.length, 12, "a far centre keeps the twelve-cell count");

assert.throws(() => hexRingWalk([0], 1), Error, "a one-element centre is rejected");
assert.throws(() => hexRingWalk([0, 0, 0], 1), Error, "a three-element centre is rejected");
assert.throws(() => hexRingWalk([0, 1.5], 1), Error, "a fractional coordinate is rejected");
assert.throws(() => hexRingWalk("00", 1), Error, "a non-address centre is rejected");
assert.throws(() => hexRingWalk([0, 0], -1), Error, "a negative radius is rejected");
assert.throws(() => hexRingWalk([0, 0], 2.5), Error, "a fractional radius is rejected");
assert.throws(() => hexRingWalk([0, 0], true), Error, "a boolean radius is rejected");
assert.throws(() => hexRingWalk([true, 0], 1), Error, "a boolean coordinate is rejected");
console.log("ok");
