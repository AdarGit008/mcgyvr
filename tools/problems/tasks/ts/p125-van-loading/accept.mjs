import assert from "node:assert/strict";
import { loadVans } from "./solution.ts";

assert.deepEqual(loadVans([4, 7, 2]), [7, 6], "heaviest first, then the lighter van");
assert.deepEqual(loadVans([5, 5, 5, 5]), [10, 10], "even totals go to the first van");
assert.deepEqual(loadVans([1]), [1, 0], "lone parcel rides the first van");
assert.deepEqual(loadVans([3, 3, 8]), [8, 6], "big parcel claims a van alone");
assert.deepEqual(loadVans([2, 9, 3, 9]), [12, 11], "equal weights keep arrival order");
assert.deepEqual(loadVans([6, 1, 1, 1, 1, 1, 1]), [6, 6], "ones trickle to balance");
assert.deepEqual(
  loadVans([1, 1, 4]),
  [4, 2],
  "the drill sorts before dispatching, not arrival order",
);
assert.throws(() => loadVans([]), Error, "empty parcel list is rejected");
assert.throws(() => loadVans([2, 0, 3]), Error, "weight below one is rejected");
console.log("ok");
