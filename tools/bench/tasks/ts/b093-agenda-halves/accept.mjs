import assert from "node:assert/strict";
import { splitAgenda } from "./solution.ts";

assert.deepEqual(splitAgenda([], 30), [], "an empty agenda has no blocks");
assert.deepEqual(splitAgenda([[0, 20]], 30), [[0, 20]], "a short session stays whole");
assert.deepEqual(splitAgenda([[0, 30]], 30), [[0, 30]], "an exact fit stays whole");
assert.deepEqual(splitAgenda([[0, 40]], 20), [[0, 20], [20, 40]], "an even cut lands on the midpoint");
assert.deepEqual(splitAgenda([[0, 45]], 25), [[0, 23], [23, 45]], "the front half takes the extra minute");
assert.deepEqual(
  splitAgenda([[0, 10]], 3),
  [[0, 3], [3, 5], [5, 8], [8, 10]],
  "halving repeats until every block fits",
);
assert.deepEqual(splitAgenda([[-4, 4]], 4), [[-4, 0], [0, 4]], "negative minutes halve cleanly");
assert.deepEqual(
  splitAgenda([[0, 10], [10, 15]], 5),
  [[0, 5], [5, 10], [10, 15]],
  "touching sessions keep their own blocks",
);
assert.deepEqual(
  splitAgenda([[0, 6], [9, 11]], 10),
  [[0, 6], [9, 11]],
  "a gap between sessions is preserved",
);
assert.throws(() => splitAgenda([[0, 10]], 0), Error, "a zero limit is rejected");
assert.throws(() => splitAgenda([[0, 10]], 2.5), Error, "a fractional limit is rejected");
assert.throws(() => splitAgenda([[5, 5]], 10), Error, "an empty session is rejected");
assert.throws(() => splitAgenda([[0, 10], [5, 12]], 20), Error, "overlapping sessions are rejected");
assert.throws(() => splitAgenda([[0, 2.5]], 10), Error, "a fractional bound is rejected");
console.log("ok");
