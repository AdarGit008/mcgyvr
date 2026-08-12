import assert from "node:assert/strict";
import { tagsOf, tagIndex } from "./solution.ts";

assert.deepEqual(tagsOf("a, b"), ["a", "b"], "the spaces are trimmed");
assert.deepEqual(tagsOf("a,,b"), ["a", "b"], "an empty tag is left out");
assert.deepEqual(tagsOf(""), [], "no tags at all");
assert.deepEqual(
  tagIndex(["a,b", "b"]),
  { a: ["a,b"], b: ["a,b", "b"] },
  "each tag names its lines",
);
assert.deepEqual(tagIndex([]), {}, "no lines at all");
assert.throws(() => tagsOf(7), Error, "a line that is not text is rejected");
console.log("ok");
