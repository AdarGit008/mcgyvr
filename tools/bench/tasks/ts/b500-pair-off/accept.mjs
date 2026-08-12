import assert from "node:assert/strict";
import { pairOff } from "./solution.ts";

assert.deepEqual(pairOff(["a", "a"]), [], "a neighbouring pair goes");
assert.deepEqual(pairOff(["a", "b", "b", "a"]), [], "the outer pair meets once the inner goes");
assert.deepEqual(pairOff(["a", "a", "b"]), ["b"], "one pair goes and a mark is left");
assert.deepEqual(pairOff(["a", "b", "a"]), ["a", "b", "a"], "no two of a kind stand together");
assert.deepEqual(pairOff(["a"]), ["a"], "a lone mark");
assert.deepEqual(pairOff([]), [], "no marks at all");
console.log("ok");
