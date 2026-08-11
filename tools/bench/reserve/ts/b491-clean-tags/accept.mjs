import assert from "node:assert/strict";
import { cleanTags } from "./solution.ts";

assert.deepEqual(cleanTags(["Red", "red", "blue"]), ["red", "blue"], "a repeat after lowering is dropped");
assert.deepEqual(cleanTags(["a1", "ok"]), ["ok"], "a tag holding a figure is turned away");
assert.deepEqual(cleanTags(["one-two"]), ["one-two"], "a dash is allowed");
assert.deepEqual(cleanTags(["A", "B", "a"]), ["a", "b"], "the arriving order is held");
assert.deepEqual(cleanTags([""]), [], "a tag holding nothing is turned away");
assert.deepEqual(cleanTags([]), [], "no tags at all");
console.log("ok");
