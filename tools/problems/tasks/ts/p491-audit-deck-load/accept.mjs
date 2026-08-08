import assert from "node:assert/strict";
import { auditDeckLoad } from "./solution.ts";

const deck = {
  bays: [
    { bay: "nose", hold: 60, lever: -3, pull: 150 },
    { bay: "core", hold: 200, lever: 0, pull: 50 },
    { bay: "tail", hold: 80, lever: 6, pull: 300 },
  ],
  total: 250,
};

assert.deepEqual(
  auditDeckLoad(
    [
      { crate: "c1", bay: "core", weight: 100 },
      { crate: "c2", bay: "nose", weight: 20 },
      { crate: "c3", bay: "tail", weight: 40 },
    ],
    deck,
  ),
  { verdict: "clear", bay: "", limit: "", weight: 160, swing: 180 },
  "a sound load reports the deck's weight and its swings added together",
);

assert.deepEqual(
  auditDeckLoad(
    [
      { crate: "c1", bay: "tail", weight: 90 },
      { crate: "c2", bay: "nose", weight: 70 },
    ],
    deck,
  ),
  { verdict: "broken", bay: "nose", limit: "hold", weight: 160, swing: 330 },
  "the deck's own order decides which failing bay is named",
);

assert.deepEqual(
  auditDeckLoad([{ crate: "k", bay: "nose", weight: 55 }], deck),
  { verdict: "broken", bay: "nose", limit: "pull", weight: 55, swing: -165 },
  "a swing is judged with its sign disregarded",
);

assert.deepEqual(
  auditDeckLoad(
    [
      { crate: "c1", bay: "nose", weight: 50 },
      { crate: "c2", bay: "core", weight: 190 },
      { crate: "c3", bay: "tail", weight: 40 },
    ],
    deck,
  ),
  { verdict: "broken", bay: "", limit: "total", weight: 280, swing: 90 },
  "total is only reached once every bay has come through",
);

assert.deepEqual(
  auditDeckLoad([{ crate: "big", bay: "core", weight: 200 }], deck),
  { verdict: "clear", bay: "", limit: "", weight: 200, swing: 0 },
  "standing exactly on a rating is not a failure",
);

assert.deepEqual(
  auditDeckLoad([], deck),
  { verdict: "clear", bay: "", limit: "", weight: 0, swing: 0 },
  "an empty deck breaks nothing and swings nothing",
);

assert.equal(
  auditDeckLoad([{ crate: "t", bay: "tail", weight: 81 }], deck).limit,
  "hold",
  "hold is tested before pull within one bay",
);

assert.throws(() => auditDeckLoad([], "deck"), Error, "deck must be a record");
assert.throws(() => auditDeckLoad([], { bays: [], total: 5 }), Error, "a deck with no bays is rejected");
assert.throws(
  () => auditDeckLoad([], { ...deck, bays: [{ bay: "", hold: 5, lever: 1, pull: 5 }] }),
  Error,
  "an empty bay name is rejected",
);
assert.throws(
  () =>
    auditDeckLoad([], {
      ...deck,
      bays: [
        { bay: "twin", hold: 5, lever: 1, pull: 5 },
        { bay: "twin", hold: 6, lever: 2, pull: 6 },
      ],
    }),
  Error,
  "a repeated bay name is rejected",
);
assert.throws(
  () => auditDeckLoad([], { ...deck, bays: [{ bay: "z", hold: 0, lever: 1, pull: 5 }] }),
  Error,
  "a hold of nought is rejected",
);
assert.throws(
  () => auditDeckLoad([], { ...deck, bays: [{ bay: "z", hold: 5, lever: 1, pull: 0 }] }),
  Error,
  "a pull of nought is rejected",
);
assert.throws(
  () => auditDeckLoad([], { ...deck, bays: [{ bay: "z", hold: 5, lever: 0.5, pull: 5 }] }),
  Error,
  "a fractional lever is rejected",
);
assert.throws(() => auditDeckLoad([], { ...deck, total: 0 }), Error, "a total of nought is rejected");
assert.throws(() => auditDeckLoad("rows", deck), Error, "rows must be a list");
assert.throws(() => auditDeckLoad([3], deck), Error, "a row must be a record");
assert.throws(
  () => auditDeckLoad([{ crate: "", bay: "core", weight: 5 }], deck),
  Error,
  "an empty crate is rejected",
);
assert.throws(
  () =>
    auditDeckLoad(
      [
        { crate: "same", bay: "core", weight: 5 },
        { crate: "same", bay: "core", weight: 6 },
      ],
      deck,
    ),
  Error,
  "a repeated crate is rejected",
);
assert.throws(
  () => auditDeckLoad([{ crate: "a", bay: "attic", weight: 5 }], deck),
  Error,
  "an unknown bay is rejected",
);
assert.throws(
  () => auditDeckLoad([{ crate: "a", bay: "core", weight: 0 }], deck),
  Error,
  "a weight of nought is rejected",
);
console.log("ok");
