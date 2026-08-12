import assert from "node:assert/strict";
import { spanLetters } from "./solution.ts";

assert.equal(spanLetters("a-e"), "abcde", "the closing letter is included");
assert.equal(spanLetters("c-d"), "cd", "a span of two letters");
assert.equal(spanLetters("a-a"), "a", "a span opening and closing on one letter");
assert.equal(spanLetters("e-a"), "e-a", "a span running backward is untouched");
assert.equal(spanLetters("hello"), "hello", "a text that is not a span");
assert.equal(spanLetters(""), "", "a text holding nothing");
console.log("ok");
