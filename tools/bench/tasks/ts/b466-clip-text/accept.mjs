import assert from "node:assert/strict";
import { clipText } from "./solution.ts";

assert.equal(clipText("abcdef", 1, 3), "bc", "the second place is left out");
assert.equal(clipText("abc", 0, 3), "abc", "the whole text");
assert.equal(clipText("abc", 1, 99), "bc", "a place past the end is brought back");
assert.equal(clipText("abc", 2, 2), "", "the two places are the same");
assert.equal(clipText("", 0, 5), "", "an empty text");
assert.throws(() => clipText("abc", 3, 1), Error, "an upside-down clip is rejected");
console.log("ok");
