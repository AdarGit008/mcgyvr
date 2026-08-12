import assert from "node:assert/strict";
import { flipTips } from "./solution.ts";

assert.equal(flipTips("abc"), "cba", "the two tips change places");
assert.equal(flipTips("hello world"), "oellh dorlw", "every word is turned");
assert.equal(flipTips("go on"), "og no", "words of exactly two characters");
assert.equal(flipTips("ab"), "ba", "a lone word of two");
assert.equal(flipTips("a"), "a", "a word too short to turn");
assert.equal(flipTips(""), "", "a line holding nothing");
console.log("ok");
