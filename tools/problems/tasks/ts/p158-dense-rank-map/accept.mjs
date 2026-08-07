import assert from "node:assert/strict";
import { denseRankMap } from "./solution.ts";

assert.deepEqual(
  denseRankMap([30, 10, 20], "asc"),
  [3, 1, 2],
  "ascending ranks land at original positions",
);
assert.deepEqual(
  denseRankMap([10, 20, 20, 30], "asc"),
  [1, 2, 2, 3],
  "a tie never swallows the next rank",
);
assert.deepEqual(
  denseRankMap([10, 20, 20, 30], "desc"),
  [3, 2, 2, 1],
  "descending flips the comparison, not the positions",
);
assert.deepEqual(
  denseRankMap([5, 1, 9], "desc"),
  [2, 3, 1],
  "descending with no ties",
);
assert.deepEqual(denseRankMap([7], "asc"), [1], "a single value ranks first");
assert.deepEqual(
  denseRankMap([4, 4, 4], "desc"),
  [1, 1, 1],
  "all equal values share rank one",
);
assert.deepEqual(
  denseRankMap([-5, 0, -5], "asc"),
  [1, 2, 1],
  "negative values rank fine",
);
assert.throws(() => denseRankMap([], "asc"), Error, "empty list is rejected");
assert.throws(
  () => denseRankMap([1.5, 2], "asc"),
  Error,
  "fractional value is rejected",
);
assert.throws(
  () => denseRankMap([1, 2], "up"),
  Error,
  "unknown order word is rejected",
);
console.log("ok");
