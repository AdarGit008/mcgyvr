import assert from "node:assert/strict";
import { swapHalves } from "./solution.ts";

assert.equal(swapHalves("abcd"), "cdab", "an even text turns about");
assert.equal(swapHalves("abc"), "cab", "the middle stays with the first half");
assert.equal(swapHalves("a"), "a", "one character cannot move");
assert.equal(swapHalves(""), "", "an empty text");
assert.equal(swapHalves("ab"), "ba", "two characters swap");
assert.equal(swapHalves("abcde"), "deabc", "five characters");
console.log("ok");
