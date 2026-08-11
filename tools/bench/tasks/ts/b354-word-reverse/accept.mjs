import assert from "node:assert/strict";
import { wordReverse } from "./solution.ts";

assert.equal(wordReverse("abc def"), "cba fed", "each word turns");
assert.equal(wordReverse("a"), "a", "one letter is its own reverse");
assert.equal(wordReverse(""), "", "an empty line");
assert.equal(wordReverse("  two  words  "), "owt sdrow", "the gaps collapse");
assert.equal(wordReverse("ab"), "ba", "a two-letter word");
assert.equal(wordReverse("one two three"), "eno owt eerht", "order is kept");
console.log("ok");
