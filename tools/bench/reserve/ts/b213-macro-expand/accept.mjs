import assert from "node:assert/strict";
import { expandMacro } from "./solution.ts";

const book = { who: "world", greet: "hello $(who)", loud: "$(greet)!" };

assert.equal(expandMacro("nothing to swap", {}), "nothing to swap", "text without references is untouched");
assert.equal(expandMacro("$(who)", book), "world", "a plain reference takes its value");
assert.equal(expandMacro("greeting: $(greet)!", book), "greeting: hello world!", "a value is read for references in turn");
assert.equal(expandMacro("$(loud)", book), "hello world!", "a macro reaches through two others");
assert.equal(expandMacro("[$(absent)]", book), "[]", "an unknown name with no fallback vanishes");
assert.equal(expandMacro("[$(absent:none set)]", book), "[none set]", "an unknown name falls back as written");
assert.throws(() => expandMacro("$(one)", { one: "$(two)", two: "$(one)" }), Error, "a cycle of macros is rejected");
console.log("ok");
