import assert from "node:assert/strict";
import { swapPair, swapAll } from "./solution.ts";

assert.equal(swapPair("a", "b"), "ba", "two characters turn round");
assert.equal(swapAll("abcd"), "badc", "two whole pairs");
assert.equal(swapAll("abc"), "bac", "the odd one stays put");
assert.equal(swapAll(""), "", "nothing to swap");
assert.equal(swapAll("a"), "a", "one character is already odd");
assert.equal(swapAll("ab"), "ba", "a single pair");
console.log("ok");
