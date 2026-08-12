import assert from "node:assert/strict";
import { maskWord, maskLine } from "./solution.ts";

assert.equal(maskWord("hello"), "h...o", "the middle is dotted");
assert.equal(maskWord("hi"), "hi", "two characters are left alone");
assert.equal(maskWord(""), "", "nothing to mask");
assert.equal(maskLine("hello there"), "h...o t...e", "every word is masked");
assert.equal(maskLine(""), "", "an empty line");
assert.equal(maskLine("a bb ccc"), "a bb c.c", "short words survive");
console.log("ok");
