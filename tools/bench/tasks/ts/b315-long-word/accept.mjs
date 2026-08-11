import assert from "node:assert/strict";
import { longWord } from "./solution.ts";

assert.equal(longWord("a bb ccc"), "ccc", "the longest wins");
assert.equal(longWord("aa bb"), "aa", "a tie goes to the first");
assert.equal(longWord(""), "", "no sentence, no word");
assert.equal(longWord("   "), "", "spaces hold no words");
assert.equal(longWord("one"), "one", "a single word");
assert.equal(longWord("to the point"), "point", "the last is longest");
console.log("ok");
