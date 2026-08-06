import assert from "node:assert/strict";
import { findAll } from "./solution.ts";

assert.deepEqual(findAll("aaaa", "aa"), [0, 1, 2], "overlapping occurrences all count");
assert.deepEqual(findAll("ababab", "abab"), [0, 2], "overlap via a proper border");
assert.deepEqual(findAll("aabaabaab", "aabaab"), [0, 3], "border of length three");
assert.deepEqual(findAll("mississippi", "issi"), [1, 4], "overlapping in real text");
assert.deepEqual(findAll("abababa", "aba"), [0, 2, 4], "every other position");
assert.deepEqual(findAll("aaabaaab", "aaab"), [0, 4], "reset after a full match");
assert.deepEqual(findAll("aaa", "aaa"), [0], "pattern equals text");
assert.deepEqual(findAll("abc", "abcd"), [], "pattern longer than text");
assert.deepEqual(findAll("", "a"), [], "empty text");
assert.deepEqual(findAll("abcabc", "xyz"), [], "no occurrence");
assert.deepEqual(findAll("xxabcxx", "abc"), [2], "single interior occurrence");
assert.throws(() => findAll("abc", ""), Error, "empty pattern throws");
