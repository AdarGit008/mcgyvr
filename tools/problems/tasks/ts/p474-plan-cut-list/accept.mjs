import assert from "node:assert/strict";
import { planCutList } from "./solution.ts";

assert.deepEqual(
  planCutList(
    [100, 100],
    [
      { length: 40, count: 3 },
      { length: 30, count: 2 },
    ],
    3,
    10,
  ),
  {
    layout: [
      [40, 40],
      [40, 30],
    ],
    offcuts: [14, 24],
    scrap: 0,
    short: [30],
  },
  "a rack of two bars runs out one piece short",
);

assert.deepEqual(
  planCutList([10], [{ length: 5, count: 2 }], 0, 1),
  { layout: [[5, 5]], offcuts: [], scrap: 0, short: [] },
  "a bar cut clean to its end leaves neither offcut nor scrap",
);

assert.deepEqual(
  planCutList([10], [{ length: 9, count: 1 }], 4, 1),
  { layout: [[9]], offcuts: [], scrap: 0, short: [] },
  "a kerf wider than the tail leaves nothing at all",
);

assert.deepEqual(
  planCutList([20], [{ length: 8, count: 2 }], 1, 5),
  { layout: [[8, 8]], offcuts: [], scrap: 2, short: [] },
  "a remainder under the keep length is scrap",
);

assert.deepEqual(
  planCutList([50, 30], [{ length: 20, count: 1 }], 2, 10),
  { layout: [[20], []], offcuts: [28, 30], scrap: 0, short: [] },
  "an untouched bar goes back on the rack whole",
);

assert.deepEqual(
  planCutList(
    [10, 10],
    [
      { length: 3, count: 1 },
      { length: 7, count: 1 },
      { length: 6, count: 1 },
    ],
    0,
    2,
  ),
  { layout: [[7, 3], [6]], offcuts: [4], scrap: 0, short: [] },
  "the longest piece is placed before the shortest whatever the order says",
);

assert.deepEqual(
  planCutList(
    [10],
    [
      { length: 11, count: 1 },
      { length: 12, count: 1 },
    ],
    0,
    1,
  ),
  { layout: [[]], offcuts: [10], scrap: 0, short: [12, 11] },
  "pieces longer than every bar are reported longest first",
);

assert.deepEqual(
  planCutList([], [{ length: 3, count: 1 }], 1, 1),
  { layout: [], offcuts: [], scrap: 0, short: [3] },
  "an empty rack cuts nothing",
);

assert.deepEqual(
  planCutList([12], [], 1, 5),
  { layout: [[]], offcuts: [12], scrap: 0, short: [] },
  "an empty order leaves the rack as it was",
);

assert.throws(
  () => planCutList("100", [], 1, 1),
  Error,
  "a bars argument that is not a list is rejected",
);
assert.throws(
  () => planCutList([0], [], 1, 1),
  Error,
  "a bar below one is rejected",
);
assert.throws(
  () => planCutList([10], "none", 1, 1),
  Error,
  "an orders argument that is not a list is rejected",
);
assert.throws(
  () => planCutList([10], [[3, 1]], 1, 1),
  Error,
  "an order that is not a mapping is rejected",
);
assert.throws(
  () => planCutList([10], [{ length: 3 }], 1, 1),
  Error,
  "an order missing its count is rejected",
);
assert.throws(
  () => planCutList([10], [{ length: 3, count: 1, grade: "a" }], 1, 1),
  Error,
  "an order carrying a spare key is rejected",
);
assert.throws(
  () => planCutList([10], [{ length: 0, count: 1 }], 1, 1),
  Error,
  "a length below one is rejected",
);
assert.throws(
  () =>
    planCutList(
      [10],
      [
        { length: 3, count: 1 },
        { length: 3, count: 2 },
      ],
      1,
      1,
    ),
  Error,
  "a length named twice is rejected",
);
assert.throws(
  () => planCutList([10], [{ length: 3, count: 0 }], 1, 1),
  Error,
  "a count below one is rejected",
);
assert.throws(
  () => planCutList([10], [], -1, 1),
  Error,
  "a kerf below nought is rejected",
);
assert.throws(
  () => planCutList([10], [], 1, -2),
  Error,
  "a keep below nought is rejected",
);
assert.throws(
  () => planCutList([10], [], 1.5, 1),
  Error,
  "a kerf that is not whole is rejected",
);
console.log("ok");
