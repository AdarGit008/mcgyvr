import assert from "node:assert/strict";
import { minWindow } from "./solution.ts";

assert.equal(minWindow("ADOBECODEBANC", "ABC"), "BANC", "classic window");
assert.equal(minWindow("a", "a"), "a", "whole string is the window");
assert.equal(minWindow("a", "aa"), "", "multiplicity cannot be met");
assert.equal(minWindow("aa", "aa"), "aa", "doubled requirement met exactly");
assert.equal(minWindow("bba", "ab"), "ba", "shorter window later in s wins");
assert.equal(
  minWindow("abXba", "ab"),
  "ab",
  "leftmost of two equal-length windows",
);
assert.equal(
  minWindow("aaflslflsldkalskaaa", "aaa"),
  "aaa",
  "window sits at the very end",
);
assert.equal(minWindow("cabwefgewcwaefgcf", "cae"), "cwae", "interior window");
assert.equal(minWindow("ADOBECODEBANC", ""), "", "empty t yields empty string");
assert.equal(minWindow("", "a"), "", "empty s yields empty string");
assert.equal(minWindow("abc", "d"), "", "required character absent");
assert.equal(minWindow("abc", "abc"), "abc", "s equals t");
assert.equal(minWindow("aA", "A"), "A", "case-sensitive matching");
