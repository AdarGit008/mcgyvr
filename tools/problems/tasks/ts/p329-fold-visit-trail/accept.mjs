import assert from "node:assert/strict";
import { foldVisitTrail } from "./solution.ts";

assert.deepEqual(foldVisitTrail([], 5), [], "no pings leave no trail");
assert.deepEqual(
  foldVisitTrail([["ida", 10]], 5),
  [["ida", [1]]],
  "a single ping is a run of one",
);
assert.deepEqual(
  foldVisitTrail(
    [
      ["ida", 30],
      ["ida", 10],
      ["ida", 12],
    ],
    5,
  ),
  [["ida", [2, 1]]],
  "the stamps are put in order before the runs are cut",
);
assert.deepEqual(
  foldVisitTrail(
    [
      ["ida", 0],
      ["ida", 5],
    ],
    5,
  ),
  [["ida", [1, 1]]],
  "a distance of exactly idle breaks the run",
);
assert.deepEqual(
  foldVisitTrail(
    [
      ["ida", 0],
      ["ida", 4],
    ],
    5,
  ),
  [["ida", [2]]],
  "one short of idle keeps the run going",
);
assert.deepEqual(
  foldVisitTrail(
    [
      ["jib", 100],
      ["ida", 0],
      ["ida", 4],
      ["jib", 90],
    ],
    5,
  ),
  [
    ["ida", [2]],
    ["jib", [1, 1]],
  ],
  "handles are answered in rising order",
);
assert.deepEqual(
  foldVisitTrail(
    [
      ["ida", 3],
      ["ida", 1],
      ["ida", 2],
    ],
    1,
  ),
  [["ida", [1, 1, 1]]],
  "an idle of one breaks between every distinct stamp",
);
assert.deepEqual(
  foldVisitTrail(
    [
      ["ida", 8],
      ["ida", 0],
      ["ida", 2],
      ["ida", 20],
      ["ida", 9],
    ],
    5,
  ),
  [["ida", [2, 2, 1]]],
  "three runs out of five scattered pings",
);

assert.throws(() => foldVisitTrail("pings", 5), Error, "a non-list is rejected");
assert.throws(
  () => foldVisitTrail([["ida", 1, 2]], 5),
  Error,
  "a ping of three items is rejected",
);
assert.throws(
  () => foldVisitTrail([["", 1]], 5),
  Error,
  "an empty handle is rejected",
);
assert.throws(
  () => foldVisitTrail([["ida", "soon"]], 5),
  Error,
  "a stamp that is not a number is rejected",
);
assert.throws(
  () =>
    foldVisitTrail(
      [
        ["ida", 7],
        ["ida", 7],
      ],
      5,
    ),
  Error,
  "one handle carrying a stamp twice is rejected",
);
assert.throws(
  () => foldVisitTrail([["ida", 1]], 0),
  Error,
  "an idle of zero is rejected",
);
assert.throws(
  () => foldVisitTrail([["ida", 1]], 2.5),
  Error,
  "a fractional idle is rejected",
);
console.log("ok");
