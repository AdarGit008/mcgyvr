import assert from "node:assert/strict";
import { advanceDunningStages } from "./solution.ts";

const book = [
  { id: "F", due: 159, cents: 90 },
  { id: "A", due: 100, cents: 5000 },
  { id: "C", due: 50, cents: 1000 },
  { id: "H", due: 145, cents: 90 },
  { id: "B", due: 130, cents: 3000 },
  { id: "G", due: 160, cents: 90 },
  { id: "D", due: 200, cents: 800 },
  { id: "E", due: 60, cents: 250 },
];
const trail = [
  { kind: "payment", day: 120, invoice: "A", cents: 1000 },
  { kind: "dispute", day: 130, invoice: "B" },
  { kind: "payment", day: 140, invoice: "C", cents: 1000 },
  { kind: "release", day: 150, invoice: "B" },
  { kind: "dispute", day: 155, invoice: "A" },
];

assert.deepEqual(
  advanceDunningStages(book, trail, 160),
  [
    { id: "A", stage: "final", owed: 4000 },
    { id: "B", stage: "reminder", owed: 3000 },
    { id: "C", stage: "settled", owed: 0 },
    { id: "D", stage: "current", owed: 800 },
    { id: "E", stage: "collections", owed: 250 },
    { id: "F", stage: "reminder", owed: 90 },
    { id: "G", stage: "current", owed: 90 },
    { id: "H", stage: "notice", owed: 90 },
  ],
  "every band, the settled case and ascending id order together",
);

assert.deepEqual(
  advanceDunningStages([{ id: "z", due: 10, cents: 500 }], [], 39),
  [{ id: "z", stage: "notice", owed: 500 }],
  "an untouched invoice ages from its due day",
);

assert.deepEqual(
  advanceDunningStages(
    [{ id: "z", due: 10, cents: 500 }],
    [
      { kind: "payment", day: 20, invoice: "z", cents: 100 },
      { kind: "payment", day: 35, invoice: "z", cents: 100 },
    ],
    39,
  ),
  [{ id: "z", stage: "reminder", owed: 300 }],
  "the most recent payment carries the anchor forward",
);

assert.deepEqual(
  advanceDunningStages(
    [{ id: "z", due: 100, cents: 500 }],
    [
      { kind: "dispute", day: 50, invoice: "z" },
      { kind: "release", day: 70, invoice: "z" },
    ],
    120,
  ),
  [{ id: "z", stage: "notice", owed: 500 }],
  "a freeze wholly before the anchor holds nothing back",
);

assert.deepEqual(
  advanceDunningStages(
    [{ id: "z", due: 100, cents: 500 }],
    [
      { kind: "dispute", day: 90, invoice: "z" },
      { kind: "release", day: 110, invoice: "z" },
    ],
    130,
  ),
  [{ id: "z", stage: "notice", owed: 500 }],
  "only the part of a freeze after the anchor is held back",
);

assert.deepEqual(
  advanceDunningStages(
    [{ id: "z", due: 0, cents: 400 }],
    [{ kind: "payment", day: 5, invoice: "z", cents: 900 }],
    500,
  ),
  [{ id: "z", stage: "settled", owed: 0 }],
  "an overpayment settles and never owes below nought",
);

assert.deepEqual(
  advanceDunningStages([], [], 7),
  [],
  "an empty book reports nothing",
);

assert.throws(
  () => advanceDunningStages([{ id: "z", due: 1, cents: 2, note: "x" }], [], 5),
  Error,
  "an invoice with a spare key is rejected",
);
assert.throws(
  () =>
    advanceDunningStages(
      [{ id: "z", due: 1, cents: 2 }, { id: "z", due: 3, cents: 4 }],
      [],
      5,
    ),
  Error,
  "two invoices sharing an id are rejected",
);
assert.throws(
  () =>
    advanceDunningStages(
      [{ id: "z", due: 1, cents: 2 }],
      [{ kind: "payment", day: 2, invoice: "q", cents: 1 }],
      5,
    ),
  Error,
  "an event naming an unheld invoice is rejected",
);
assert.throws(
  () =>
    advanceDunningStages(
      [{ id: "z", due: 1, cents: 2 }],
      [{ kind: "release", day: 2, invoice: "z" }],
      5,
    ),
  Error,
  "releasing an unfrozen invoice is rejected",
);
assert.throws(
  () =>
    advanceDunningStages(
      [{ id: "z", due: 1, cents: 2 }],
      [
        { kind: "dispute", day: 2, invoice: "z" },
        { kind: "dispute", day: 3, invoice: "z" },
      ],
      5,
    ),
  Error,
  "disputing a frozen invoice again is rejected",
);
assert.throws(
  () =>
    advanceDunningStages(
      [{ id: "z", due: 1, cents: 2 }],
      [{ kind: "payment", day: 9, invoice: "z", cents: 1 }],
      5,
    ),
  Error,
  "an event past the reporting day is rejected",
);
assert.throws(
  () =>
    advanceDunningStages(
      [{ id: "z", due: 1, cents: 2 }],
      [
        { kind: "dispute", day: 4, invoice: "z" },
        { kind: "release", day: 3, invoice: "z" },
      ],
      5,
    ),
  Error,
  "an event day stepping backwards is rejected",
);
assert.throws(
  () => advanceDunningStages([{ id: "z", due: 1, cents: 0 }], [], 5),
  Error,
  "an invoice for nothing is rejected",
);
assert.throws(
  () => advanceDunningStages([{ id: "z", due: 1, cents: 2 }], [], -1),
  Error,
  "a reporting day below nought is rejected",
);
console.log("ok");
