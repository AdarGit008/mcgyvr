import assert from "node:assert/strict";
import { dupeKeys } from "./solution.ts";

assert.deepEqual(dupeKeys(["a", "b", "a"]), ["a"], "one repeat");
assert.deepEqual(dupeKeys(["a", "a", "a"]), ["a"], "reported once however often");
assert.deepEqual(dupeKeys(["a", "b", "c"]), [], "no repeats at all");
assert.deepEqual(dupeKeys([]), [], "nothing in, nothing out");
assert.deepEqual(dupeKeys(["b", "a", "b", "a"]), ["b", "a"], "in order of first repeat");
assert.deepEqual(dupeKeys(["x", "y", "y", "x"]), ["y", "x"], "the inner pair repeats first");
console.log("ok");
