import assert from "node:assert/strict";
import { inBoth, sharedOf } from "./solution.ts";

assert.equal(inBoth("a", ["a"], ["a"]), true, "held by both");
assert.equal(inBoth("a", ["a"], ["b"]), false, "held by one only");
assert.deepEqual(sharedOf(["a", "b"], ["b", "c"]), ["b"], "one entry is shared");
assert.deepEqual(sharedOf(["a"], ["b"]), [], "nothing is shared");
assert.deepEqual(sharedOf([], ["a"]), [], "an empty first list");
assert.deepEqual(sharedOf(["a", "a"], ["a"]), ["a"], "a repeat is reported once");
console.log("ok");
