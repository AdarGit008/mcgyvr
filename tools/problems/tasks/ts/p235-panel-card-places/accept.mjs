import assert from "node:assert/strict";
import { placeCards } from "./solution.ts";

const panel = {
  width: 100,
  height: 60,
  bleed: 5,
  cardWidth: 20,
  cardHeight: 10,
  seam: 5,
};
const tight = {
  width: 60,
  height: 20,
  bleed: 0,
  cardWidth: 20,
  cardHeight: 10,
  seam: 0,
};

assert.deepEqual(placeCards(panel, 0, []), [], "asking for none lays none");
assert.deepEqual(
  placeCards(panel, 4, []),
  [
    [5, 5],
    [30, 5],
    [55, 5],
    [5, 20],
  ],
  "reading order wraps to the row beneath after the last column",
);
assert.deepEqual(
  placeCards(panel, 2, [1, 3]),
  [
    [30, 5],
    [5, 20],
  ],
  "spoken-for cells are stepped over",
);
assert.deepEqual(
  placeCards(panel, 1, [9, 9, 2, 2]),
  [[5, 5]],
  "a cell named twice is still one cell",
);
assert.deepEqual(
  placeCards(panel, 8, [5])[7],
  [55, 35],
  "the bottom-right cell sits a full grid from the bleed",
);
assert.equal(placeCards(panel, 9, []).length, 9, "the grid here holds nine");
assert.deepEqual(
  placeCards(tight, 5, []),
  [
    [0, 0],
    [20, 0],
    [40, 0],
    [0, 10],
    [20, 10],
  ],
  "no bleed and no seam puts the first corner at the origin",
);
assert.throws(
  () => placeCards(panel, 9, [5]),
  Error,
  "one cell spoken for leaves too few for nine",
);
assert.throws(
  () => placeCards(panel, 1, [10]),
  Error,
  "a cell number past the grid is rejected",
);
assert.throws(
  () => placeCards(panel, 1, [0]),
  Error,
  "cells are numbered from one, so zero is rejected",
);
assert.throws(
  () =>
    placeCards(
      { width: 10, height: 10, bleed: 1, cardWidth: 20, cardHeight: 5, seam: 0 },
      1,
      [],
    ),
  Error,
  "a panel too small for a single card is refused",
);
assert.throws(() => placeCards(panel, -1, []), Error, "a negative count is rejected");
assert.throws(
  () => placeCards({ ...panel, seam: -2 }, 1, []),
  Error,
  "a negative seam is rejected",
);
console.log("ok");
