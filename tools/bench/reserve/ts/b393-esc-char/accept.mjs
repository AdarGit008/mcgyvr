import assert from "node:assert/strict";
import { escChar } from "./solution.ts";

assert.equal(escChar("a,b", ","), "a^,b", "the marked character is escaped");
assert.equal(escChar("ab", ","), "ab", "nothing to escape");
assert.equal(escChar("", ","), "", "an empty text");
assert.equal(escChar("a^b", ","), "a^^b", "a caret already there is escaped");
assert.equal(escChar(",,", ","), "^,^,", "two in a row");
assert.equal(escChar("a", "a"), "^a", "the whole text is escaped");
console.log("ok");
