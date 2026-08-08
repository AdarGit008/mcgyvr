import assert from "node:assert/strict";
import { gappedMatch } from "./solution.ts";

assert.equal(gappedMatch("abc", "abc", 0), true, "exact text matches with gap 0");
assert.equal(gappedMatch("abc", "axbxc", 1), true, "one skip between letters");
assert.equal(gappedMatch("abc", "axbxc", 0), false, "gap 0 forbids those skips");
assert.equal(
  gappedMatch("abc", "abxabc", 0),
  true,
  "the earliest start fails but a later one works",
);
assert.equal(
  gappedMatch("aab", "aaxab", 0),
  false,
  "no placement satisfies gap 0 here",
);
assert.equal(
  gappedMatch("aab", "aaxab", 1),
  true,
  "gap 1 lets the second a re-anchor",
);
assert.equal(gappedMatch("zz", "zaz", 0), false, "adjacent needed, one apart given");
assert.equal(gappedMatch("zz", "zaz", 1), true, "one apart allowed by gap 1");
assert.equal(gappedMatch("a", "xxxa", 0), true, "leading characters are free");
assert.equal(gappedMatch("aba", "xxabya", 5), true, "generous gap, late start");
assert.equal(gappedMatch("abcd", "abc", 3), false, "needle longer than haystack");
assert.throws(() => gappedMatch("", "abc", 1), Error, "empty needle rejected");
assert.throws(() => gappedMatch("a", "abc", -1), Error, "negative gap rejected");
assert.throws(() => gappedMatch("a", "abc", 1.5), Error, "fractional gap rejected");
console.log("ok");
