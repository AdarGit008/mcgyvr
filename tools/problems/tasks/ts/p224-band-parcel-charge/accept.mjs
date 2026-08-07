import assert from "node:assert/strict";
import { bandParcelCharge } from "./solution.ts";

const BOOK = {
  zones: ["home", "near", "far"],
  steps: [
    { upTo: 500, cents: [299, 399, 599] },
    { upTo: 2000, cents: [499, 699, 999] },
    { upTo: null, cents: [899, 1299, 1899] },
  ],
  extras: [
    { mark: "fragile", cents: 150, zones: null },
    { mark: "rush", cents: 250, zones: ["near", "far"] },
  ],
  round: 5,
};

const PLAIN = { zones: ["z"], steps: [{ upTo: null, cents: [100] }], extras: [], round: 5 };
const PARCEL = { zone: "z", grams: 10, marks: [] };

function bent(patch) {
  return { ...PLAIN, ...patch };
}

assert.deepEqual(
  bandParcelCharge(BOOK, { zone: "home", grams: 500, marks: [] }),
  { band: 0, base: 299, extra: 0, total: 300, applied: [] },
  "a parcel sitting exactly on a band's weight stays in that band",
);

assert.deepEqual(
  bandParcelCharge(BOOK, { zone: "home", grams: 501, marks: [] }),
  { band: 1, base: 499, extra: 0, total: 500, applied: [] },
  "one gram past the edge moves it up a band",
);

assert.deepEqual(
  bandParcelCharge(BOOK, { zone: "far", grams: 5000, marks: ["rush", "fragile"] }),
  { band: 2, base: 1899, extra: 400, total: 2300, applied: ["fragile", "rush"] },
  "the open band catches the heavy parcel, and the charges follow the book's order",
);

assert.deepEqual(
  bandParcelCharge(BOOK, { zone: "home", grams: 100, marks: ["rush"] }),
  { band: 0, base: 299, extra: 0, total: 300, applied: [] },
  "a charge that does not cover the zone is not made",
);

assert.deepEqual(
  bandParcelCharge(BOOK, { zone: "near", grams: 2000, marks: ["fragile"] }),
  { band: 1, base: 699, extra: 150, total: 850, applied: ["fragile"] },
  "the middle band with one charge on top",
);

assert.deepEqual(
  bandParcelCharge(BOOK, { zone: "near", grams: 2001, marks: [] }),
  { band: 2, base: 1299, extra: 0, total: 1300, applied: [] },
  "the price is read from the parcel's own zone column",
);

assert.deepEqual(
  bandParcelCharge(PLAIN, PARCEL),
  { band: 0, base: 100, extra: 0, total: 100, applied: [] },
  "a sum already sitting on a multiple is left alone",
);

assert.deepEqual(
  bandParcelCharge({ ...BOOK, round: 1 }, { zone: "home", grams: 1, marks: ["fragile"] }),
  { band: 0, base: 299, extra: 150, total: 449, applied: ["fragile"] },
  "rounding to one cent changes nothing",
);

assert.deepEqual(
  bandParcelCharge({ ...BOOK, round: 100 }, { zone: "far", grams: 1, marks: [] }),
  { band: 0, base: 599, extra: 0, total: 600, applied: [] },
  "a coarse rounding step lifts the sum a long way",
);

assert.throws(() => bandParcelCharge([], PARCEL), Error, "a book that is not a mapping is rejected");
assert.throws(() => bandParcelCharge(PLAIN, "z"), Error, "a parcel that is not a mapping is rejected");
assert.throws(() => bandParcelCharge(bent({ zones: [] }), PARCEL), Error, "an empty zone list is rejected");
assert.throws(() => bandParcelCharge(bent({ zones: ["z", "z"] }), PARCEL), Error, "a zone listed twice is rejected");
assert.throws(() => bandParcelCharge(bent({ zones: [""] }), PARCEL), Error, "an empty zone name is rejected");
assert.throws(() => bandParcelCharge(bent({ steps: [] }), PARCEL), Error, "a book with no bands is rejected");
assert.throws(() => bandParcelCharge(bent({ steps: ["x"] }), PARCEL), Error, "a band that is not a mapping is rejected");
assert.throws(
  () => bandParcelCharge(bent({ steps: [{ upTo: "500", cents: [1] }, { upTo: null, cents: [2] }] }), PARCEL),
  Error,
  "a stated weight that is not a number is rejected",
);
assert.throws(
  () => bandParcelCharge(bent({ steps: [{ upTo: 0, cents: [1] }, { upTo: null, cents: [2] }] }), PARCEL),
  Error,
  "a stated weight of zero is rejected",
);
assert.throws(
  () =>
    bandParcelCharge(
      bent({ steps: [{ upTo: 500, cents: [1] }, { upTo: 500, cents: [2] }, { upTo: null, cents: [3] }] }),
      PARCEL,
    ),
  Error,
  "stated weights that do not climb are rejected",
);
assert.throws(
  () => bandParcelCharge(bent({ steps: [{ upTo: null, cents: [1] }, { upTo: 500, cents: [2] }] }), PARCEL),
  Error,
  "an open band that is not last is rejected",
);
assert.throws(
  () => bandParcelCharge(bent({ steps: [{ upTo: 500, cents: [1] }] }), PARCEL),
  Error,
  "a book with no open band is rejected",
);
assert.throws(
  () => bandParcelCharge(bent({ steps: [{ upTo: null, cents: [1, 2] }] }), PARCEL),
  Error,
  "a price list longer than the zone list is rejected",
);
assert.throws(
  () => bandParcelCharge(bent({ steps: [{ upTo: null, cents: [-1] }] }), PARCEL),
  Error,
  "a negative price is rejected",
);
assert.throws(() => bandParcelCharge(bent({ extras: "x" }), PARCEL), Error, "extras that are not a list are rejected");
assert.throws(
  () =>
    bandParcelCharge(
      bent({ extras: [{ mark: "m", cents: 1, zones: null }, { mark: "m", cents: 2, zones: null }] }),
      PARCEL,
    ),
  Error,
  "a mark charged twice is rejected",
);
assert.throws(
  () => bandParcelCharge(bent({ extras: [{ mark: "m", cents: 1, zones: ["nowhere"] }] }), PARCEL),
  Error,
  "a charge naming an unknown zone is rejected",
);
assert.throws(
  () => bandParcelCharge(bent({ extras: [{ mark: "m", cents: -5, zones: null }] }), PARCEL),
  Error,
  "a negative charge is rejected",
);
assert.throws(() => bandParcelCharge(bent({ round: 0 }), PARCEL), Error, "a rounding step of zero is rejected");
assert.throws(() => bandParcelCharge(PLAIN, { ...PARCEL, zone: "q" }), Error, "an unknown parcel zone is rejected");
assert.throws(() => bandParcelCharge(PLAIN, { ...PARCEL, grams: 0 }), Error, "grams of zero are rejected");
assert.throws(() => bandParcelCharge(PLAIN, { ...PARCEL, grams: 1.5 }), Error, "fractional grams are rejected");
assert.throws(() => bandParcelCharge(PLAIN, { ...PARCEL, marks: "m" }), Error, "marks that are not a list are rejected");
assert.throws(() => bandParcelCharge(PLAIN, { ...PARCEL, marks: ["nope"] }), Error, "a mark the book never names is rejected");
assert.throws(
  () => bandParcelCharge(bent({ extras: [{ mark: "m", cents: 1, zones: null }] }), { ...PARCEL, marks: ["m", "m"] }),
  Error,
  "a mark carried twice is rejected",
);
console.log("ok");
