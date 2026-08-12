import assert from "node:assert/strict";
import { nearestDepot, taxiDistance } from "./solution.ts";

assert.equal(taxiDistance([0, 0], [3, 4]), 7, "blocks east plus blocks south");
assert.equal(taxiDistance([2, -1], [-2, 3]), 8, "both differences count as magnitudes");
assert.equal(nearestDepot([0, 0], [[5, 0], [1, 1], [0, 3]]), 1, "closest of three depots");
assert.equal(nearestDepot([2, 2], [[2, 2]]), 0, "a lone depot wins");
assert.equal(
  nearestDepot([0, 0], [[2, 0], [0, 2], [1, 1]]),
  0,
  "a distance tie goes to the lowest index",
);
assert.equal(
  nearestDepot([0, 0], [[1, 0], [-4, 0]]),
  0,
  "a depot west of the origin is not nearer than it is",
);
assert.equal(
  nearestDepot([0, 0], [[0, -6], [0, 2]]),
  1,
  "a depot north of the origin is not nearer than it is",
);
assert.equal(nearestDepot([3, 3], [[3, 3], [4, 4]]), 0, "standing at a depot is distance zero");
assert.throws(() => nearestDepot([0, 0], []), Error, "empty depot list is rejected");
assert.throws(() => nearestDepot([0, 0], [[1.5, 0]]), Error, "fractional depot coordinate");
assert.throws(() => nearestDepot([0.5, 0], [[1, 0]]), Error, "fractional origin coordinate");
console.log("ok");
