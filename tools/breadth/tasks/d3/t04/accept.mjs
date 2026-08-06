import assert from "node:assert/strict";
import { lcs } from "./solution.ts";

assert.equal(lcs("ba", "ab"), "a", "one-char tie picks the smaller character");
assert.equal(lcs("ab", "ba"), "a", "same tie with arguments swapped");
assert.equal(lcs("bac", "abc"), "ac", "'ac' beats the equally long 'bc'");
assert.equal(lcs("abab", "baba"), "aba", "'aba' beats the equally long 'bab'");
assert.equal(lcs("bdcaba", "abcbdab"), "bcab", "length-4 tie resolves to 'bcab'");
assert.equal(lcs("cbacba", "abcabc"), "aba", "length-3 tie resolves to 'aba'");
assert.equal(lcs("zaz", "az"), "az", "unique LCS is returned as-is");
assert.equal(lcs("same", "same"), "same", "identical inputs");
assert.equal(lcs("abc", "xyz"), "", "no shared characters");
assert.equal(lcs("", "abc"), "", "empty first input");
assert.equal(lcs("abc", ""), "", "empty second input");
assert.equal(
  lcs("qwabcdefgqw", "zxabcdefgzx"),
  "abcdefg",
  "long unique LCS survives surrounding noise",
);
assert.equal(
  lcs("bca", "abca"),
  "bca",
  "starting with the smaller 'a' would cost length, so 'bca' wins",
);
assert.equal(lcs("zzzazzzb", "ab"), "ab", "sparse characters across noise");
