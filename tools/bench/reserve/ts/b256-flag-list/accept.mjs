import assert from "node:assert/strict";
import { flagList } from "./solution.ts";

assert.deepEqual(flagList("-a -b"), ["a", "b"], "two flags, dashes stripped");
assert.deepEqual(flagList("-a file"), ["a"], "a plain word is not a flag");
assert.deepEqual(flagList("file"), [], "no flags on the line");
assert.deepEqual(flagList(""), [], "an empty line");
assert.deepEqual(flagList("-x"), ["x"], "a single flag");
assert.deepEqual(flagList("-a -a"), ["a", "a"], "a repeated flag is kept twice");
console.log("ok");
