import assert from "node:assert/strict";
import { quoteFreightRun } from "./solution.ts";

const BANDS = [
  { from: 0, perKilo: 100 },
  { from: 5, perKilo: 80 },
  { from: 20, perKilo: 50 },
];

assert.deepEqual(
  quoteFreightRun(BANDS, 7),
  { split: [500, 160, 0], cents: 660 },
  "the run crosses into the second band and stops there",
);

assert.deepEqual(
  quoteFreightRun(BANDS, 5),
  { split: [500, 0, 0], cents: 500 },
  "a weight landing on a band's start leaves that band with nothing yet",
);

assert.deepEqual(
  quoteFreightRun(BANDS, 4),
  { split: [400, 0, 0], cents: 400 },
  "a run wholly inside the first band",
);

assert.deepEqual(
  quoteFreightRun(BANDS, 1),
  { split: [100, 0, 0], cents: 100 },
  "the smallest consignment there is",
);

assert.deepEqual(
  quoteFreightRun(BANDS, 20),
  { split: [500, 1200, 0], cents: 1700 },
  "the middle band charges its whole stretch and no more",
);

assert.deepEqual(
  quoteFreightRun(BANDS, 21),
  { split: [500, 1200, 50], cents: 1750 },
  "the last band picks up everything beyond its start",
);

assert.deepEqual(
  quoteFreightRun([{ from: 0, perKilo: 250 }], 3),
  { split: [750], cents: 750 },
  "one band charges the whole run",
);

assert.deepEqual(
  quoteFreightRun([{ from: 0, perKilo: 0 }], 9),
  { split: [0], cents: 0 },
  "a free rate charges nothing however heavy the run",
);

assert.throws(() => quoteFreightRun("bands", 3), Error, "bands that are not a list are rejected");
assert.throws(() => quoteFreightRun([], 3), Error, "an empty band list is rejected");
assert.throws(() => quoteFreightRun([["from", 0]], 3), Error, "a band that is not a mapping is rejected");
assert.throws(() => quoteFreightRun([{ from: 1, perKilo: 100 }], 3), Error, "a first band starting above nought is rejected");
assert.throws(
  () => quoteFreightRun([{ from: 0, perKilo: 1 }, { from: 0, perKilo: 2 }], 3),
  Error,
  "starting weights that do not climb are rejected",
);
assert.throws(
  () => quoteFreightRun([{ from: 0, perKilo: 1 }, { from: 4, perKilo: 2 }, { from: 2, perKilo: 3 }], 3),
  Error,
  "a starting weight that falls back is rejected",
);
assert.throws(() => quoteFreightRun([{ from: 0, perKilo: -1 }], 3), Error, "a negative rate is rejected");
assert.throws(() => quoteFreightRun([{ from: 0, perKilo: 1.5 }], 3), Error, "a fractional rate is rejected");
assert.throws(() => quoteFreightRun([{ from: "0", perKilo: 1 }], 3), Error, "a starting weight that is not a number is rejected");
assert.throws(() => quoteFreightRun(BANDS, 0), Error, "a weightless consignment is rejected");
assert.throws(() => quoteFreightRun(BANDS, 2.5), Error, "a fractional weight is rejected");
assert.throws(() => quoteFreightRun(BANDS, "3"), Error, "a weight that is not a number is rejected");
console.log("ok");
