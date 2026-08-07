import assert from "node:assert/strict";
import { chainTransforms } from "./solution.ts";

const grid = [[1, 2, 3], [4, 5, 6]];
assert.deepEqual(chainTransforms(grid, ["cw"]), [[4, 1], [5, 2], [6, 3]], "quarter turn clockwise");
assert.deepEqual(
  chainTransforms(grid, ["ccw"]),
  [[3, 6], [2, 5], [1, 4]],
  "quarter turn counterclockwise",
);
assert.deepEqual(chainTransforms(grid, ["mirror"]), [[3, 2, 1], [6, 5, 4]], "left-right flip");
assert.deepEqual(chainTransforms(grid, ["flip"]), [[4, 5, 6], [1, 2, 3]], "top-bottom flip");
assert.deepEqual(
  chainTransforms(grid, ["diag"]),
  [[1, 4], [2, 5], [3, 6]],
  "main-diagonal reflection",
);
assert.deepEqual(chainTransforms(grid, ["cw", "cw"]), [[6, 5, 4], [3, 2, 1]], "two turns");
assert.deepEqual(
  chainTransforms(grid, ["cw", "flip"]),
  [[6, 3], [5, 2], [4, 1]],
  "steps compose in the order given",
);
assert.deepEqual(
  chainTransforms(grid, ["diag", "mirror"]),
  [[4, 1], [5, 2], [6, 3]],
  "reflection then mirror equals one clockwise turn",
);
assert.deepEqual(chainTransforms(grid, []), [[1, 2, 3], [4, 5, 6]], "the empty chain is a copy");
assert.deepEqual(grid, [[1, 2, 3], [4, 5, 6]], "the argument grid is never modified");
assert.throws(() => chainTransforms(grid, ["spin"]), Error, "an unknown step is rejected");
assert.throws(() => chainTransforms([], ["cw"]), Error, "a grid with no rows is rejected");
assert.throws(
  () => chainTransforms([[1, 2], [3]], ["cw"]),
  Error,
  "ragged rows are rejected",
);
console.log("ok");
