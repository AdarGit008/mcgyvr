import assert from "node:assert/strict";
import { wordTally } from "./solution.ts";

assert.deepEqual(wordTally("a b a"), { a: 2, b: 1 }, "one word twice");
assert.deepEqual(wordTally("A a"), { a: 2 }, "case is ignored");
assert.deepEqual(wordTally(""), {}, "no sentence, no tally");
assert.deepEqual(wordTally("  x   y  "), { x: 1, y: 1 }, "wide gaps are one break");
assert.deepEqual(wordTally("one"), { one: 1 }, "a single word");
assert.deepEqual(wordTally("go go go"), { go: 3 }, "three of a kind");
console.log("ok");
