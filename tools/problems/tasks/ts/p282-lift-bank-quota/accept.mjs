import assert from "node:assert/strict";
import { assignLiftCalls } from "./solution.ts";

const pair = [
  { name: "A", floor: 0, quota: 3 },
  { name: "B", floor: 5, quota: 3 },
];

assert.deepEqual(
  assignLiftCalls(pair, [4, 1, 8], 9),
  ["B", "A", "B"],
  "nearest standing cage answers, and it then stands at the call",
);
assert.deepEqual(assignLiftCalls(pair, [], 9), [], "no calls, no names");
assert.deepEqual(
  assignLiftCalls(
    [
      { name: "Z", floor: 2, quota: 5 },
      { name: "A", floor: 4, quota: 5 },
    ],
    [3],
    6,
  ),
  ["A"],
  "equal nearness and equal load falls to the earlier name, not list order",
);
assert.deepEqual(
  assignLiftCalls(
    [
      { name: "A", floor: 0, quota: 5 },
      { name: "B", floor: 0, quota: 5 },
    ],
    [0, 0, 0],
    4,
  ),
  ["A", "B", "A"],
  "the lighter load wins before the name does",
);
assert.deepEqual(
  assignLiftCalls(
    [
      { name: "A", floor: 0, quota: 1 },
      { name: "B", floor: 9, quota: 1 },
    ],
    [1, 2, 3],
    9,
  ),
  ["A", "B", "-"],
  "a spent bank marks the call and moves nobody",
);
assert.deepEqual(
  assignLiftCalls([{ name: "solo", floor: 3, quota: 4 }], [7, 7, 0], 7),
  ["solo", "solo", "solo"],
  "one cage answers until its quota runs out",
);
assert.deepEqual(
  assignLiftCalls(
    [
      { name: "A", floor: 0, quota: 2 },
      { name: "B", floor: 10, quota: 2 },
      { name: "C", floor: 5, quota: 2 },
    ],
    [6, 6, 6, 6, 6, 6],
    10,
  ),
  ["C", "C", "B", "B", "A", "A"],
  "a longer run drains every quota in turn",
);

assert.throws(() => assignLiftCalls([], [1], 5), Error, "empty bank");
assert.throws(
  () =>
    assignLiftCalls(
      [
        { name: "A", floor: 0, quota: 1 },
        { name: "A", floor: 1, quota: 1 },
      ],
      [1],
      5,
    ),
  Error,
  "repeated name",
);
assert.throws(
  () => assignLiftCalls([{ name: "-", floor: 0, quota: 1 }], [1], 5),
  Error,
  "the mark cannot be a cage name",
);
assert.throws(
  () => assignLiftCalls([{ name: "A", floor: 6, quota: 1 }], [1], 5),
  Error,
  "standing above the top floor",
);
assert.throws(
  () => assignLiftCalls([{ name: "A", floor: 0, quota: 0 }], [1], 5),
  Error,
  "quota below one",
);
assert.throws(
  () => assignLiftCalls([{ name: "A", floor: 0, quota: 1 }], [-1], 5),
  Error,
  "call below the ground floor",
);
assert.throws(
  () => assignLiftCalls([{ name: "A", floor: 0, quota: 1 }], [2.5], 5),
  Error,
  "a fractional call",
);
assert.throws(
  () => assignLiftCalls([{ name: "A", floor: 0, quota: 1 }], [1], 0),
  Error,
  "a building with no upper floor",
);
console.log("ok");
