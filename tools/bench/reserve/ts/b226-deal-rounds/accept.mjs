import assert from "node:assert/strict";
import { dealRounds } from "./solution.ts";

assert.deepEqual(dealRounds("abcdef", 2), ["ace", "bdf"], "an even deck across two piles");
assert.deepEqual(dealRounds("abcdef", 3), ["ad", "be", "cf"], "an even deck across three piles");
assert.deepEqual(dealRounds("abcde", 2), ["ace", "bd"], "an odd card leaves the second pile short");
assert.deepEqual(dealRounds("xyz", 1), ["xyz"], "one pile takes the deck in order");
assert.deepEqual(dealRounds("", 4), ["", "", "", ""], "an empty deck yields one empty pile per hand");
assert.deepEqual(dealRounds("ab", 5), ["a", "b", "", "", ""], "more piles than cards leaves later piles empty");
assert.deepEqual(dealRounds("aabb", 2), ["ab", "ab"], "repeated cards keep their dealt places");
assert.throws(() => dealRounds(42, 2), Error, "a deck that is not a string is rejected");
assert.throws(() => dealRounds("abc", 0), Error, "a hand count below one is rejected");
assert.throws(() => dealRounds("abc", 2.5), Error, "a fractional hand count is rejected");
console.log("ok");
