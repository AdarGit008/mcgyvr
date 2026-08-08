import assert from "node:assert/strict";
import { smallestArrangement } from "./solution.ts";

assert.equal(smallestArrangement([1]), "a", "single letter");
assert.equal(smallestArrangement([2]), "aa", "a double run is allowed");
assert.equal(smallestArrangement([2, 1]), "aab", "simple greedy case");
assert.equal(smallestArrangement([3, 1]), "aaba", "run must break at two");
assert.equal(smallestArrangement([4, 1]), "aabaa", "separator splits two doubles");
assert.equal(smallestArrangement([2, 2]), "aabb", "double double");
assert.equal(smallestArrangement([1, 1, 1]), "abc", "three distinct letters");
assert.equal(smallestArrangement([0, 2]), "bb", "leading zero count skips a");
assert.equal(
  smallestArrangement([2, 4]),
  "abbabb",
  "greedy without lookahead strands the b's"
);
assert.equal(
  smallestArrangement([0, 1, 0, 3]),
  "dbdd",
  "the lone b must be spent as a separator, not spent first"
);
assert.throws(() => smallestArrangement([3]), Error, "three of one letter alone");
assert.throws(() => smallestArrangement([5, 1]), Error, "too few separators");
assert.throws(() => smallestArrangement([]), Error, "empty list");
assert.throws(() => smallestArrangement([1, 1, 1, 1, 1]), Error, "too many counts");
assert.throws(() => smallestArrangement([0, 0]), Error, "all zero");
assert.throws(() => smallestArrangement([13]), Error, "count above cap");
assert.throws(() => smallestArrangement([-1, 2]), Error, "negative count");
assert.throws(() => smallestArrangement([1.5, 1]), Error, "fractional count");
console.log("ok");
