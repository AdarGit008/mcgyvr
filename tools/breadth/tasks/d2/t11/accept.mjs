import assert from "node:assert/strict";
import { maxSlidingWindow } from "./solution.ts";

assert.deepEqual(
  maxSlidingWindow([1, 3, -1, -3, 5, 3, 6, 7], 3),
  [3, 3, 5, 5, 6, 7],
  "classic case"
);
assert.deepEqual(maxSlidingWindow([4], 1), [4], "single element");
assert.deepEqual(maxSlidingWindow([9, 2, 7], 3), [9], "k equals length");
assert.deepEqual(maxSlidingWindow([5, 1, 5], 1), [5, 1, 5], "k of one copies the array");
assert.deepEqual(maxSlidingWindow([2, 2, 2, 2], 2), [2, 2, 2], "all duplicates");
assert.deepEqual(maxSlidingWindow([-7, -3, -9, -1], 2), [-3, -3, -1], "all negative");
assert.deepEqual(
  maxSlidingWindow([9, 8, 7, 6, 5], 2),
  [9, 8, 7, 6],
  "strictly decreasing input evicts the leaver"
);
assert.deepEqual(
  maxSlidingWindow([1, 2, 3, 4, 5], 2),
  [2, 3, 4, 5],
  "strictly increasing input"
);

// Large deterministic case: 500k pseudo-random values (fixed formula, no RNG),
// k = 5000. An O(n*k) rescan is ~2.5e9 operations and will not finish in time;
// the O(n) deque finishes in well under a second. Spot-check sampled windows
// against a directly computed maximum.
const n = 500000;
const k = 5000;
const big = new Array(n);
for (let i = 0; i < n; i++) big[i] = (i * 2654435761) % 1000003;
const out = maxSlidingWindow(big, k);
assert.equal(out.length, n - k + 1, "large case result length");
for (const start of [0, 1, 4999, 123456, 250000, n - k]) {
  let expected = -Infinity;
  for (let i = start; i < start + k; i++) {
    if (big[i] > expected) expected = big[i];
  }
  assert.equal(out[start], expected, `large case window at ${start}`);
}

assert.throws(() => maxSlidingWindow([1, 2], 3), Error, "k beyond length throws");
assert.throws(() => maxSlidingWindow([1, 2], 0), Error, "k of zero throws");
assert.throws(() => maxSlidingWindow([], 1), Error, "empty array throws");
assert.throws(() => maxSlidingWindow([1, 2, 3], 1.5), Error, "fractional k throws");
