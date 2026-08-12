import assert from "node:assert/strict";
import { indexMap } from "./solution.ts";

assert.deepEqual(indexMap(["a", "b", "a"]), { a: [0, 2], b: [1] }, "two places");
assert.deepEqual(indexMap(["x"]), { x: [0] }, "one label, one place");
assert.deepEqual(indexMap([]), {}, "no labels at all");
assert.deepEqual(indexMap(["a", "a", "a"]), { a: [0, 1, 2] }, "the same label thrice");
assert.deepEqual(indexMap(["b", "a"]), { b: [0], a: [1] }, "each holds one place");
assert.deepEqual(indexMap(["a", "b", "b"]), { a: [0], b: [1, 2] }, "a later pair");
console.log("ok");
