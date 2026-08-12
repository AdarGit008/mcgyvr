import assert from "node:assert/strict";
import { slugWord, slugMake } from "./solution.ts";

assert.equal(slugWord("Hello!"), "hello", "punctuation is dropped");
assert.equal(slugWord("--"), "", "a word may slug away entirely");
assert.equal(slugMake("Hello, World!"), "hello-world", "joined with a hyphen");
assert.equal(slugMake("a -- b"), "a-b", "an empty slug is left out");
assert.equal(slugMake(""), "", "nothing to slug");
assert.equal(slugMake("Top 10 Tips"), "top-10-tips", "digits survive");
console.log("ok");
