import assert from "node:assert/strict";
import { preloadPicks } from "./solution.ts";

const entry = (key, size, hits) => ({ key, size, hits });

assert.deepEqual(preloadPicks([], 10), [], "no candidates, nothing taken");
assert.deepEqual(
  preloadPicks([entry("a", 4, 2)], 10),
  ["a"],
  "a candidate that fits is taken"
);
assert.deepEqual(
  preloadPicks([entry("a", 40, 2)], 10),
  [],
  "a candidate too large is passed over"
);
assert.deepEqual(preloadPicks([entry("a", 1, 2)], 0), [], "no room, nothing taken");
assert.deepEqual(
  preloadPicks([entry("a", 1, 1), entry("b", 1, 5), entry("c", 1, 3)], 3),
  ["b", "c", "a"],
  "the line runs from most hits to fewest"
);
assert.deepEqual(
  preloadPicks([entry("a", 9, 5), entry("b", 2, 5)], 20),
  ["b", "a"],
  "equal hits favour the smaller size"
);
assert.deepEqual(
  preloadPicks([entry("zed", 2, 5), entry("abe", 2, 5)], 10),
  ["abe", "zed"],
  "equal hits and size favour the earlier key"
);
assert.deepEqual(
  preloadPicks([entry("big", 6, 9), entry("small", 5, 1)], 5),
  ["small"],
  "the line carries on past a candidate that will not fit"
);
assert.deepEqual(
  preloadPicks([entry("a", 4, 9), entry("b", 3, 8), entry("c", 2, 7)], 6),
  ["a", "c"],
  "a later candidate takes the room the middle one could not"
);
assert.deepEqual(
  preloadPicks([entry("a", 5, 1), entry("b", 5, 2)], 10),
  ["b", "a"],
  "the room runs out exactly"
);

assert.throws(
  () => preloadPicks("abc", 5),
  Error,
  "a candidate list that is not a list is rejected"
);
assert.throws(
  () => preloadPicks([], -1),
  Error,
  "a negative room is rejected"
);
assert.throws(
  () => preloadPicks([], 2.5),
  Error,
  "a room that is not whole is rejected"
);
assert.throws(
  () => preloadPicks([["a", 1, 1]], 5),
  Error,
  "a candidate that is not a mapping is rejected"
);
assert.throws(
  () => preloadPicks([{ size: 1, hits: 1 }], 5),
  Error,
  "a missing key is rejected"
);
assert.throws(
  () => preloadPicks([entry("", 1, 1)], 5),
  Error,
  "an empty key is rejected"
);
assert.throws(
  () => preloadPicks([entry("a", 1, 1), entry("a", 2, 2)], 5),
  Error,
  "a repeated key is rejected"
);
assert.throws(
  () => preloadPicks([entry("a", 0, 1)], 5),
  Error,
  "a size of zero is rejected"
);
assert.throws(
  () => preloadPicks([entry("a", 1, -1)], 5),
  Error,
  "negative hits are rejected"
);

console.log("ok");
