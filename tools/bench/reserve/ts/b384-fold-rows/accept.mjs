import assert from "node:assert/strict";
import { rowWidest, foldRows } from "./solution.ts";

assert.equal(rowWidest([[1], [1, 2, 3]]), 3, "the longest row wins");
assert.equal(rowWidest([]), 0, "no rows at all");
assert.deepEqual(
  foldRows([[1], [1, 2, 3]]),
  [[1, 0, 0], [1, 2, 3]],
  "the short row is padded out",
);
assert.deepEqual(foldRows([]), [], "no rows fold to no rows");
assert.deepEqual(foldRows([[1, 2], [3, 4]]), [[1, 2], [3, 4]], "nothing needs padding");
assert.deepEqual(foldRows([[], [7]]), [[0], [7]], "an empty row is padded");
console.log("ok");
