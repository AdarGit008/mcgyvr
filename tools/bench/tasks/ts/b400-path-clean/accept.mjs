import assert from "node:assert/strict";
import { pathClean } from "./solution.ts";

assert.equal(pathClean("a/b/.."), "a", "the step back removes one segment");
assert.equal(pathClean("a/.."), "", "back to nothing");
assert.equal(pathClean(".."), "", "nothing to step back from");
assert.equal(pathClean("a/b"), "a/b", "no steps back at all");
assert.equal(pathClean(""), "", "an empty path");
assert.equal(pathClean("a/../b"), "b", "a step back in the middle");
console.log("ok");
