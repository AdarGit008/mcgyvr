import assert from "node:assert/strict";
import { flipOne, flipAll } from "./solution.ts";

assert.deepEqual(flipOne(["a", "b"]), ["b", "a"], "one pair turns round");
assert.deepEqual(flipOne(["x", "x"]), ["x", "x"], "a pair of the same");
assert.deepEqual(flipAll([["a", "b"], ["c", "d"]]), [["b", "a"], ["d", "c"]], "each pair");
assert.deepEqual(flipAll([]), [], "no pairs at all");
assert.deepEqual(flipAll([["a", "b"]]), [["b", "a"]], "a single pair");

const source = [["a", "b"]];
flipAll(source);
assert.deepEqual(source, [["a", "b"]], "the list it was given is untouched");
console.log("ok");
