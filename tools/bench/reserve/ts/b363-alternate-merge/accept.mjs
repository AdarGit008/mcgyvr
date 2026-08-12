import assert from "node:assert/strict";
import { alternateMerge } from "./solution.ts";

assert.deepEqual(alternateMerge(["a", "b"], ["1", "2"]), ["a", "1", "b", "2"], "in turn");
assert.deepEqual(alternateMerge(["a"], ["1", "2"]), ["a", "1", "2"], "the right runs on");
assert.deepEqual(alternateMerge(["a", "b"], ["1"]), ["a", "1", "b"], "the left runs on");
assert.deepEqual(alternateMerge([], []), [], "two empty lists");
assert.deepEqual(alternateMerge([], ["1"]), ["1"], "only the right holds anything");
assert.deepEqual(alternateMerge(["a"], []), ["a"], "only the left holds anything");
console.log("ok");
