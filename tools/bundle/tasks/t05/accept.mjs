import assert from "node:assert/strict";
import { chunk } from "./solution.ts";

assert.deepEqual(chunk([1, 2, 3, 4, 5], 2), [[1, 2], [3, 4], [5]], "uneven final group");
assert.deepEqual(chunk([1, 2, 3, 4], 2), [[1, 2], [3, 4]], "even division");
assert.deepEqual(chunk([], 3), [], "empty input yields no groups");
assert.deepEqual(chunk([1], 1), [[1]], "single element");
assert.deepEqual(chunk([1, 2], 5), [[1, 2]], "size larger than the array is one group");
assert.deepEqual(chunk(["a", "b", "c"], 1), [["a"], ["b"], ["c"]], "size one");

const input = [1, 2, 3];
const snapshot = JSON.stringify(input);
const groups = chunk(input, 2);
assert.equal(JSON.stringify(input), snapshot, "input must not be mutated");
groups[0][0] = 99;
assert.equal(input[0], 1, "groups must not alias the input array");

for (const bad of [0, -1, 2.5, "2"]) {
  assert.throws(() => chunk([1, 2], bad), Error, `size ${JSON.stringify(bad)} throws`);
}
