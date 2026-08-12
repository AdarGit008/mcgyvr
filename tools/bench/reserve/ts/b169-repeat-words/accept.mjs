import assert from "node:assert/strict";
import { repeatWords } from "./solution.ts";

assert.deepEqual(repeatWords("the cat and the hat", 2), ["the"], "one word reaches the bar");
assert.deepEqual(repeatWords("Sun sun SUN moon", 2), ["sun"], "counting folds case and lowercases the answer");
assert.deepEqual(repeatWords("red blue red", 1), ["red", "blue"], "least one lists every distinct word once");
assert.deepEqual(repeatWords("one two three", 2), [], "no word reaching the bar yields the empty list");
assert.deepEqual(repeatWords("", 2), [], "an empty text yields the empty list");
assert.deepEqual(repeatWords("b a b a a c", 2), ["b", "a"], "winners keep first-appearance order");
assert.deepEqual(repeatWords("hi  hi", 2), ["hi"], "a run of spaces is one separator");
assert.throws(() => repeatWords(42, 2), Error, "a non-string text is rejected");
assert.throws(() => repeatWords("big deal!", 2), Error, "a character outside letters and spaces is rejected");
assert.throws(() => repeatWords("big deal", 0), Error, "a least below one is rejected");
assert.throws(() => repeatWords("big deal", 2.5), Error, "a fractional least is rejected");
console.log("ok");
