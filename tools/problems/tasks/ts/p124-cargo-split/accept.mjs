import assert from "node:assert/strict";
import { splitCargo } from "./solution.ts";

assert.deepEqual(
  splitCargo([3, 1, 1, 2, 2, 1]),
  [0, 3],
  "even split, fewest items, then lexicographic",
);
assert.deepEqual(
  splitCargo([5, 5, 4]),
  [0],
  "fewer items preferred at equal difference",
);
assert.deepEqual(splitCargo([7]), [0], "single item stows forward");
assert.deepEqual(splitCargo([2, 2]), [0], "pair splits one each");
assert.deepEqual(
  splitCargo([2, 2, 2, 2]),
  [0, 1],
  "lexicographic tie-break among equal-size stowages",
);
assert.deepEqual(splitCargo([8, 3, 3, 4]), [0], "heavy head sails alone");
assert.deepEqual(splitCargo([10, 7, 5, 4]), [0, 3], "closest achievable is two apart");
assert.throws(() => splitCargo([]), Error, "empty manifest is rejected");
assert.throws(() => splitCargo([3, 0, 2]), Error, "weight below one is rejected");
console.log("ok");
