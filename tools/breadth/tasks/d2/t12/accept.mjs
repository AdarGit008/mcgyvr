import assert from "node:assert/strict";
import { editDistance } from "./solution.ts";

assert.equal(editDistance("", ""), 0, "both empty");
assert.equal(editDistance("", "abc"), 3, "insertions from empty");
assert.equal(editDistance("abc", ""), 3, "deletions to empty");
assert.equal(editDistance("kitten", "kitten"), 0, "identical strings");
assert.equal(editDistance("kitten", "sitting"), 3, "classic kitten/sitting");
assert.equal(editDistance("flaw", "lawn"), 2, "shift by one plus append");
assert.equal(editDistance("ab", "ba"), 2, "transposition costs two");
assert.equal(editDistance("a", "A"), 1, "case-sensitive comparison");
assert.equal(editDistance("intention", "execution"), 5, "textbook example");
assert.equal(editDistance("abcdef", "azced"), 3, "mixed operations");
assert.equal(editDistance("x", "y"), 1, "single substitution");
assert.equal(editDistance("horse", "ros"), 3, "leetcode example");

// Long input: 1000 characters forces a polynomial algorithm.
const long1 = "ab".repeat(500);
const long2 = "ba".repeat(500);
assert.equal(editDistance(long1, long1), 0, "1000-char identity");
assert.equal(editDistance(long1, long2), 2, "abab...ab vs baba...ba is two edits");
assert.equal(editDistance("a".repeat(1000), "a".repeat(600)), 400, "long deletion run");

assert.throws(() => editDistance(1, "a"), Error, "non-string first argument throws");
assert.throws(() => editDistance("a", null), Error, "non-string second argument throws");
