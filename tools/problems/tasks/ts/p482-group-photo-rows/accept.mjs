import assert from "node:assert/strict";
import { groupPhotoRows } from "./solution.ts";

const sheet = { width: 100, band: 20, gap: 4 };
const mixed = [
  { tag: "A", wide: 10, high: 20 },
  { tag: "B", wide: 40, high: 20 },
  { tag: "C", wide: 20, high: 20 },
  { tag: "D", wide: 5, high: 20 },
  { tag: "E", wide: 30, high: 10 },
];

assert.deepEqual(
  groupPhotoRows(mixed, sheet),
  [
    { family: "upright", tags: ["A", "D"], run: 19, spare: 81 },
    { family: "oblong", tags: ["B"], run: 40, spare: 60 },
    { family: "oblong", tags: ["E"], run: 60, spare: 40 },
    { family: "square", tags: ["C"], run: 20, spare: 80 },
  ],
  "families are laid upright, oblong, square and never share a band",
);

assert.deepEqual(
  groupPhotoRows(
    [
      { tag: "P", wide: 10, high: 10 },
      { tag: "Q", wide: 10, high: 10 },
      { tag: "R", wide: 10, high: 10 },
      { tag: "S", wide: 10, high: 10 },
    ],
    { width: 30, band: 10, gap: 0 },
  ),
  [
    { family: "square", tags: ["P", "Q", "R"], run: 30, spare: 0 },
    { family: "square", tags: ["S"], run: 10, spare: 20 },
  ],
  "a band filled to the width leaves no spare and the next picture opens a band",
);

assert.deepEqual(
  groupPhotoRows(
    [
      { tag: "F", wide: 7, high: 3 },
      { tag: "G", wide: 3, high: 7 },
    ],
    { width: 200, band: 20, gap: 2 },
  ),
  [
    { family: "upright", tags: ["G"], run: 8, spare: 192 },
    { family: "oblong", tags: ["F"], run: 46, spare: 154 },
  ],
  "printed widths round down and family order beats arrival order",
);

assert.deepEqual(
  groupPhotoRows([{ tag: "solo", wide: 4, high: 8 }], {
    width: 50,
    band: 16,
    gap: 3,
  }),
  [{ family: "upright", tags: ["solo"], run: 8, spare: 42 }],
  "one picture makes one band",
);

const wide = groupPhotoRows(mixed, { width: 300, band: 20, gap: 5 });
assert.equal(wide.length, 3, "a roomy sheet gives one band per family");
assert.deepEqual(
  wide.map((row) => row.tags.join("")),
  ["AD", "BE", "C"],
  "each family keeps arrival order on its own band",
);

assert.throws(() => groupPhotoRows("nope", sheet), Error, "photos must be a list");
assert.throws(() => groupPhotoRows([], sheet), Error, "an empty list is rejected");
assert.throws(() => groupPhotoRows([7], sheet), Error, "a photo must be a record");
assert.throws(
  () => groupPhotoRows([{ tag: "", wide: 4, high: 4 }], sheet),
  Error,
  "an empty tag is rejected",
);
assert.throws(
  () =>
    groupPhotoRows(
      [
        { tag: "T", wide: 4, high: 4 },
        { tag: "T", wide: 5, high: 5 },
      ],
      sheet,
    ),
  Error,
  "a repeated tag is rejected",
);
assert.throws(
  () => groupPhotoRows([{ tag: "T", wide: 0, high: 4 }], sheet),
  Error,
  "a side of nought is rejected",
);
assert.throws(
  () => groupPhotoRows([{ tag: "T", wide: 4, high: 2.5 }], sheet),
  Error,
  "a fractional side is rejected",
);
assert.throws(
  () => groupPhotoRows([{ tag: "T", wide: 4, high: 4 }], [100, 20, 4]),
  Error,
  "sheet must be a record",
);
assert.throws(
  () =>
    groupPhotoRows([{ tag: "T", wide: 4, high: 4 }], {
      width: 0,
      band: 20,
      gap: 4,
    }),
  Error,
  "a width of nought is rejected",
);
assert.throws(
  () =>
    groupPhotoRows([{ tag: "T", wide: 4, high: 4 }], {
      width: 100,
      band: 20,
      gap: -1,
    }),
  Error,
  "a negative gap is rejected",
);
assert.throws(
  () => groupPhotoRows([{ tag: "T", wide: 1, high: 30 }], sheet),
  Error,
  "a picture printing to nothing is rejected",
);
assert.throws(
  () => groupPhotoRows([{ tag: "T", wide: 200, high: 20 }], sheet),
  Error,
  "a picture wider than the sheet is rejected",
);
console.log("ok");
