import assert from "node:assert/strict";
import { sentenceSplit } from "./solution.ts";

assert.deepEqual(sentenceSplit("One. Two."), ["One", "Two"], "full stops break");
assert.deepEqual(sentenceSplit("Who? Me!"), ["Who", "Me"], "the other marks break too");
assert.deepEqual(sentenceSplit("No ending"), ["No ending"], "an unfinished sentence");
assert.deepEqual(sentenceSplit(""), [], "nothing to break");
assert.deepEqual(sentenceSplit("..."), [], "empty pieces are left out");
assert.deepEqual(sentenceSplit("A! B. C?"), ["A", "B", "C"], "all three marks");
console.log("ok");
