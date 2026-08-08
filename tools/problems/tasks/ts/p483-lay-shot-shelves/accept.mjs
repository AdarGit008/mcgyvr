import assert from "node:assert/strict";
import { layShotShelves } from "./solution.ts";

const strip = { perRow: 3, cell: 60, lead: 4 };
const shots = [
  { name: "s1", across: 60, down: 40 },
  { name: "s2", across: 30, down: 40 },
  { name: "s3", across: 45, down: 30 },
  { name: "s4", across: 7, down: 3 },
  { name: "s5", across: 8, down: 8 },
];

assert.deepEqual(
  layShotShelves(shots, strip),
  {
    rows: [
      { names: ["s1", "s2", "s3"], deep: 80 },
      { names: ["s4", "s5"], deep: 60 },
    ],
    deep: 144,
  },
  "a row runs as deep as its deepest frame and one lead joins the two rows",
);

assert.deepEqual(
  layShotShelves([{ name: "only", across: 7, down: 3 }], {
    perRow: 3,
    cell: 60,
    lead: 9,
  }),
  { rows: [{ names: ["only"], deep: 26 }], deep: 26 },
  "a remainder pushes the depth up and a single row carries no lead",
);

assert.deepEqual(
  layShotShelves([{ name: "even", across: 20, down: 10 }], {
    perRow: 4,
    cell: 100,
    lead: 3,
  }),
  { rows: [{ names: ["even"], deep: 50 }], deep: 50 },
  "an exact division is not pushed up",
);

assert.deepEqual(
  layShotShelves(shots.slice(0, 3), { perRow: 1, cell: 60, lead: 5 }),
  {
    rows: [
      { names: ["s1"], deep: 40 },
      { names: ["s2"], deep: 80 },
      { names: ["s3"], deep: 40 },
    ],
    deep: 170,
  },
  "three rows carry two leads",
);

assert.equal(
  layShotShelves(shots, { perRow: 3, cell: 60, lead: 0 }).deep,
  140,
  "a lead of nought adds nothing",
);
assert.deepEqual(
  layShotShelves(shots, { perRow: 5, cell: 60, lead: 7 }).rows.map(
    (row) => row.names.length,
  ),
  [5],
  "one row holds every frame when perRow allows it",
);

assert.throws(() => layShotShelves("nope", strip), Error, "shots must be a list");
assert.throws(() => layShotShelves([], strip), Error, "an empty list is rejected");
assert.throws(() => layShotShelves(["s1"], strip), Error, "a shot must be a record");
assert.throws(
  () => layShotShelves([{ name: "", across: 4, down: 4 }], strip),
  Error,
  "an empty name is rejected",
);
assert.throws(
  () =>
    layShotShelves(
      [
        { name: "twin", across: 4, down: 4 },
        { name: "twin", across: 5, down: 5 },
      ],
      strip,
    ),
  Error,
  "a repeated name is rejected",
);
assert.throws(
  () => layShotShelves([{ name: "z", across: 0, down: 4 }], strip),
  Error,
  "a side of nought is rejected",
);
assert.throws(
  () => layShotShelves([{ name: "z", across: 4, down: 1.5 }], strip),
  Error,
  "a fractional side is rejected",
);
assert.throws(
  () => layShotShelves([{ name: "z", across: 4, down: 4 }], "strip"),
  Error,
  "strip must be a record",
);
assert.throws(
  () =>
    layShotShelves([{ name: "z", across: 4, down: 4 }], {
      perRow: 0,
      cell: 60,
      lead: 4,
    }),
  Error,
  "a perRow of nought is rejected",
);
assert.throws(
  () =>
    layShotShelves([{ name: "z", across: 4, down: 4 }], {
      perRow: 3,
      cell: 60,
      lead: -2,
    }),
  Error,
  "a negative lead is rejected",
);
console.log("ok");
