import assert from "node:assert/strict";
import { flatlineSpans } from "./solution.ts";

assert.deepEqual(
  flatlineSpans([1, 1, 1, 2, 2, 3], 2),
  [
    [0, 2],
    [3, 4],
  ],
  "a stretch exactly as long as least counts",
);
assert.deepEqual(flatlineSpans([4, 4, 4], 3), [[0, 2]], "a stretch may fill the channel");
assert.deepEqual(flatlineSpans([4, 4, 4], 4), [], "a stretch shorter than least is dropped");
assert.deepEqual(
  flatlineSpans([2, 2, 3, 3, 3], 3),
  [[2, 4]],
  "the stretch closing the channel is reported",
);
assert.deepEqual(
  flatlineSpans([2, 2, 2, 3, 4, 4], 2),
  [
    [0, 2],
    [4, 5],
  ],
  "several stretches come back in opening order",
);
assert.deepEqual(flatlineSpans([0, 0, 0, 0], 2), [[0, 3]], "one maximal stretch, not many");
assert.deepEqual(flatlineSpans([7, 8, 9], 2), [], "a channel that never repeats is flat nowhere");
assert.deepEqual(flatlineSpans([], 2), [], "an empty channel reports nothing");
assert.deepEqual(flatlineSpans([5], 2), [], "a single sample is too short");
assert.deepEqual(
  flatlineSpans([-3, -3, -3, -3, 6], 4),
  [[0, 3]],
  "negative samples repeat like any other",
);

assert.throws(() => flatlineSpans([1, 1], 1), Error, "a least of one is rejected");
assert.throws(() => flatlineSpans([1, 1], 2.5), Error, "a fractional least is rejected");
assert.throws(() => flatlineSpans([1, 1], "3"), Error, "a non-numeric least is rejected");
console.log("ok");
