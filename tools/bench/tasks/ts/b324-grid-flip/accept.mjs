import assert from "node:assert/strict";
import { gridFlip } from "./solution.ts";

assert.deepEqual(gridFlip([[1, 2], [3, 4]]), [[1, 3], [2, 4]], "a square turns");
assert.deepEqual(gridFlip([[1, 2, 3]]), [[1], [2], [3]], "one row becomes three");
assert.deepEqual(gridFlip([[1], [2]]), [[1, 2]], "one column becomes one row");
assert.deepEqual(gridFlip([]), [], "no rows at all");
assert.deepEqual(gridFlip([[]]), [], "a row holding nothing");
assert.deepEqual(
  gridFlip([[1, 2], [3, 4], [5, 6]]),
  [[1, 3, 5], [2, 4, 6]],
  "three rows become two",
);
console.log("ok");
