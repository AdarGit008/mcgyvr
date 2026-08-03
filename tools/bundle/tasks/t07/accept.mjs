import assert from "node:assert/strict";
import { flatten } from "./solution.ts";

assert.deepEqual(flatten([1, [2, [3, [4]]]]), [1, 2, 3, 4], "flattens every level by default");
assert.deepEqual(flatten([]), [], "empty input");
assert.deepEqual(flatten([1, 2, 3]), [1, 2, 3], "already flat");
assert.deepEqual(flatten([1, [2, [3, [4]]]], 1), [1, 2, [3, [4]]], "depth one");
assert.deepEqual(flatten([1, [2, [3]]], 0), [1, [2, [3]]], "depth zero is a copy");
assert.deepEqual(flatten([[], [[]]]), [], "empty nested arrays vanish");
assert.deepEqual(flatten([1, [null, undefined]]), [1, null, undefined], "holes are values");

// A string is iterable in JavaScript. The contract says it is a value.
assert.deepEqual(flatten(["ab", ["cd"]]), ["ab", "cd"], "strings are not flattened");
assert.deepEqual(flatten([["x"]], Infinity), ["x"], "a nested string survives whole");

const input = [1, [2]];
const snapshot = JSON.stringify(input);
const result = flatten(input, 0);
assert.equal(JSON.stringify(input), snapshot, "input must not be mutated");
assert.notEqual(result, input, "depth zero returns a copy, not the same array");

for (const bad of [-1, 1.5, "2"]) {
  assert.throws(() => flatten([1], bad), Error, `depth ${JSON.stringify(bad)} throws`);
}
