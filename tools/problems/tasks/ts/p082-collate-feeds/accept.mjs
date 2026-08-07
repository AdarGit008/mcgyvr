import assert from "node:assert/strict";
import { collateFeeds } from "./solution.ts";

assert.deepEqual(
  collateFeeds([[[1, 5], [4, 7]], [[2, 6], [3, 7]]]),
  [[1, 5], [2, 6], [3, 7]],
  "interleave, then drop the repeated reading at tick 4",
);
assert.deepEqual(
  collateFeeds([[[5, 1]], [[5, 2]]]),
  [[5, 1]],
  "tick tie goes to the earliest feed",
);
assert.deepEqual(
  collateFeeds([[[5, 9]], [[5, 2]], [[5, 4]]]),
  [[5, 9]],
  "three-way tie still goes to feed 0",
);
assert.deepEqual(
  collateFeeds([[[1, 5], [3, 6]], [[2, 5]]]),
  [[1, 5], [3, 6]],
  "a reading repeated across feeds is thinned",
);
assert.deepEqual(
  collateFeeds([[[1, 4], [2, 4], [3, 5]]]),
  [[1, 4], [3, 5]],
  "a reading repeated within one feed is thinned",
);
assert.deepEqual(collateFeeds([[], [[7, 3]], []]), [[7, 3]], "empty feeds contribute nothing");
assert.deepEqual(collateFeeds([]), [], "no feeds at all");
assert.deepEqual(collateFeeds([[], []]), [], "only empty feeds");
assert.deepEqual(
  collateFeeds([[[1, 2], [2, 3], [3, 2]]]),
  [[1, 2], [2, 3], [3, 2]],
  "a reading may return after an intervening change",
);
assert.throws(
  () => collateFeeds([[[3, 1], [3, 2]]]),
  Error,
  "equal ticks inside one feed are rejected",
);
assert.throws(
  () => collateFeeds([[[1, 1]], [[5, 2], [4, 3]]]),
  Error,
  "decreasing ticks inside one feed are rejected",
);
console.log("ok");
