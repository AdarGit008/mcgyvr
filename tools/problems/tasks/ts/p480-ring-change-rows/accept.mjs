import assert from "node:assert/strict";
import { ringChangeRows } from "./solution.ts";

assert.deepEqual(
  ringChangeRows(4, [[], [1, 4]], 9),
  [
    [1, 2, 3, 4],
    [2, 1, 4, 3],
    [2, 4, 1, 3],
    [4, 2, 3, 1],
    [4, 3, 2, 1],
    [3, 4, 1, 2],
    [3, 1, 4, 2],
    [1, 3, 2, 4],
    [1, 2, 3, 4],
  ],
  "two changes taken in turn bring four bells back to rounds",
);

assert.deepEqual(
  ringChangeRows(4, [[], [1, 4]], 1),
  [[1, 2, 3, 4]],
  "a count of one gives back rounds alone",
);

assert.deepEqual(
  ringChangeRows(2, [[]], 3),
  [
    [1, 2],
    [2, 1],
    [1, 2],
  ],
  "two bells swap and swap back",
);

assert.deepEqual(
  ringChangeRows(6, [[1, 6]], 2),
  [
    [1, 2, 3, 4, 5, 6],
    [1, 3, 2, 5, 4, 6],
  ],
  "the four bells between two standing places pair off from the left",
);

assert.deepEqual(
  ringChangeRows(
    4,
    [
      [1, 2],
      [3, 4],
    ],
    4,
  ),
  [
    [1, 2, 3, 4],
    [1, 2, 4, 3],
    [2, 1, 4, 3],
    [2, 1, 3, 4],
  ],
  "changes are taken up again from the first once the last is rung",
);

assert.deepEqual(
  ringChangeRows(3, [[3]], 3),
  [
    [1, 2, 3],
    [2, 1, 3],
    [1, 2, 3],
  ],
  "a standing place at the back leaves the front pair to swap",
);

assert.deepEqual(
  ringChangeRows(4, [[]], 3),
  [
    [1, 2, 3, 4],
    [2, 1, 4, 3],
    [1, 2, 3, 4],
  ],
  "a change with nothing standing swaps every pair",
);

assert.throws(
  () => ringChangeRows(1, [[]], 2),
  Error,
  "fewer than two bells is rejected",
);
assert.throws(
  () => ringChangeRows(13, [[]], 2),
  Error,
  "more than twelve bells is rejected",
);
assert.throws(
  () => ringChangeRows(2.5, [[]], 2),
  Error,
  "a bells argument that is not whole is rejected",
);
assert.throws(
  () => ringChangeRows(4, "14", 2),
  Error,
  "a changes argument that is not a list is rejected",
);
assert.throws(
  () => ringChangeRows(4, [], 2),
  Error,
  "an empty changes argument is rejected",
);
assert.throws(
  () => ringChangeRows(4, ["14"], 2),
  Error,
  "a change that is not a list is rejected",
);
assert.throws(
  () => ringChangeRows(4, [[0]], 2),
  Error,
  "a place below one is rejected",
);
assert.throws(
  () => ringChangeRows(4, [[5]], 2),
  Error,
  "a place past the last bell is rejected",
);
assert.throws(
  () => ringChangeRows(4, [[2, 1]], 2),
  Error,
  "places that do not climb are rejected",
);
assert.throws(
  () => ringChangeRows(4, [[1, 1]], 2),
  Error,
  "a place written twice is rejected",
);
assert.throws(
  () => ringChangeRows(4, [[2]], 2),
  Error,
  "a change leaving an odd run of movers is rejected",
);
assert.throws(
  () => ringChangeRows(3, [[]], 2),
  Error,
  "an odd peal with nothing standing is rejected",
);
assert.throws(
  () => ringChangeRows(4, [[]], 0),
  Error,
  "a count below one is rejected",
);
console.log("ok");
