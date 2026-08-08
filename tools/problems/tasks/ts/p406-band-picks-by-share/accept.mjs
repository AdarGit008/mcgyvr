import assert from "node:assert/strict";
import { bandPicksByShare } from "./solution.ts";

const stock = [
  { code: "K7", picks: 600 },
  { code: "B2", picks: 250 },
  { code: "A9", picks: 80 },
  { code: "M1", picks: 40 },
  { code: "Z3", picks: 20 },
  { code: "Q5", picks: 10 },
];
const aisle = [
  { code: "R1", capacity: 1 },
  { code: "R2", capacity: 2 },
  { code: "R3", capacity: 2 },
  { code: "R4", capacity: 4 },
];

assert.deepEqual(
  bandPicksByShare(stock, [70, 90], aisle),
  [
    { code: "K7", band: "A", row: "R1", slot: 1 },
    { code: "B2", band: "A", row: "R2", slot: 1 },
    { code: "A9", band: "B", row: "R3", slot: 1 },
    { code: "M1", band: "C", row: "R4", slot: 1 },
    { code: "Z3", band: "C", row: "R4", slot: 2 },
    { code: "Q5", band: "C", row: "R4", slot: 3 },
  ],
  "three bands, each starting on its own row",
);

assert.deepEqual(
  bandPicksByShare(stock, [55, 90], aisle),
  [
    { code: "K7", band: "A", row: "R1", slot: 1 },
    { code: "B2", band: "B", row: "R2", slot: 1 },
    { code: "A9", band: "B", row: "R2", slot: 2 },
    { code: "M1", band: "C", row: "R3", slot: 1 },
    { code: "Z3", band: "C", row: "R3", slot: 2 },
    { code: "Q5", band: "C", row: "R4", slot: 1 },
  ],
  "a tighter first cut moves the split, and a full row opens the next",
);

assert.deepEqual(
  bandPicksByShare(
    [
      { code: "D", picks: 50 },
      { code: "C", picks: 50 },
      { code: "A", picks: 100 },
    ],
    [50, 80],
    [
      { code: "F1", capacity: 1 },
      { code: "F2", capacity: 3 },
    ],
  ),
  [
    { code: "A", band: "A", row: "F1", slot: 1 },
    { code: "C", band: "B", row: "F2", slot: 1 },
    { code: "D", band: "B", row: "F2", slot: 2 },
  ],
  "equal picks rank by code, and an empty band takes no row",
);

assert.deepEqual(
  bandPicksByShare(
    [
      { code: "X", picks: 70 },
      { code: "Y", picks: 20 },
      { code: "Z", picks: 10 },
    ],
    [70, 90],
    [{ code: "W", capacity: 1 }, { code: "V", capacity: 1 }, { code: "U", capacity: 1 }],
  ),
  [
    { code: "X", band: "A", row: "W", slot: 1 },
    { code: "Y", band: "B", row: "V", slot: 1 },
    { code: "Z", band: "C", row: "U", slot: 1 },
  ],
  "landing exactly on a cut sends the line to the next band",
);

assert.deepEqual(
  bandPicksByShare(
    [
      { code: "S", picks: 5 },
      { code: "T", picks: 0 },
    ],
    [40, 90],
    [{ code: "G1", capacity: 5 }, { code: "G2", capacity: 5 }],
  ),
  [
    { code: "S", band: "A", row: "G1", slot: 1 },
    { code: "T", band: "C", row: "G2", slot: 1 },
  ],
  "a line never pulled falls to the last band",
);

assert.throws(() => bandPicksByShare("x", [70, 90], aisle), Error, "lines not a list");
assert.throws(() => bandPicksByShare([], [70, 90], aisle), Error, "no lines at all");
assert.throws(() => bandPicksByShare([7], [70, 90], aisle), Error, "a line that is not a record");
assert.throws(
  () => bandPicksByShare([{ code: "", picks: 3 }], [70, 90], aisle),
  Error,
  "an empty code",
);
assert.throws(
  () =>
    bandPicksByShare(
      [
        { code: "A", picks: 3 },
        { code: "A", picks: 4 },
      ],
      [70, 90],
      aisle,
    ),
  Error,
  "one code twice",
);
assert.throws(
  () => bandPicksByShare([{ code: "A", picks: -1 }], [70, 90], aisle),
  Error,
  "negative picks",
);
assert.throws(
  () => bandPicksByShare([{ code: "A", picks: 0 }], [70, 90], aisle),
  Error,
  "nothing pulled at all",
);
assert.throws(() => bandPicksByShare(stock, [70], aisle), Error, "only one cut");
assert.throws(() => bandPicksByShare(stock, [0, 90], aisle), Error, "a cut below one");
assert.throws(() => bandPicksByShare(stock, [70, 100], aisle), Error, "a cut above ninety-nine");
assert.throws(() => bandPicksByShare(stock, [90, 70], aisle), Error, "cuts the wrong way round");
assert.throws(() => bandPicksByShare(stock, [70, 90], []), Error, "no rows at all");
assert.throws(() => bandPicksByShare(stock, [70, 90], [{ code: "R1" }]), Error, "no capacity");
assert.throws(
  () => bandPicksByShare(stock, [70, 90], [{ code: "R1", capacity: 0 }]),
  Error,
  "a capacity of nothing",
);
assert.throws(
  () =>
    bandPicksByShare(stock, [70, 90], [
      { code: "R1", capacity: 2 },
      { code: "R1", capacity: 2 },
    ]),
  Error,
  "one row code twice",
);
assert.throws(
  () => bandPicksByShare(stock, [70, 90], [{ code: "R1", capacity: 2 }]),
  Error,
  "the rows run out",
);
console.log("ok");
