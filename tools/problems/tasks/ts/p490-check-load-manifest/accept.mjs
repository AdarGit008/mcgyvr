import assert from "node:assert/strict";
import { checkLoadManifest } from "./solution.ts";

const plan = {
  zones: [
    { zone: "fore", cap: 100, arm: -2 },
    { zone: "mid", cap: 200, arm: 0 },
    { zone: "aft", cap: 120, arm: 4 },
  ],
  gross: 300,
  low: -150,
  high: 150,
};

assert.deepEqual(
  checkLoadManifest(
    [
      { tag: "a", zone: "mid", mass: 50 },
      { tag: "b", zone: "aft", mass: 30 },
      { tag: "c", zone: "aft", mass: 20 },
    ],
    plan,
  ),
  {
    loaded: ["a", "b"],
    stopped: "c",
    limit: "moment",
    mass: 80,
    moment: 120,
    zones: [
      { zone: "fore", mass: 0 },
      { zone: "mid", mass: 50 },
      { zone: "aft", mass: 30 },
    ],
  },
  "the moment window bites and the item is left off",
);

assert.deepEqual(
  checkLoadManifest(
    [
      { tag: "a", zone: "fore", mass: 60 },
      { tag: "b", zone: "fore", mass: 50 },
      { tag: "c", zone: "mid", mass: 10 },
    ],
    plan,
  ),
  {
    loaded: ["a"],
    stopped: "b",
    limit: "cap",
    mass: 60,
    moment: -120,
    zones: [
      { zone: "fore", mass: 60 },
      { zone: "mid", mass: 0 },
      { zone: "aft", mass: 0 },
    ],
  },
  "a zone cap is tested first and the items behind are never tried",
);

assert.deepEqual(
  checkLoadManifest(
    [
      { tag: "a", zone: "hold", mass: 60 },
      { tag: "b", zone: "hold", mass: 50 },
    ],
    { zones: [{ zone: "hold", cap: 1000, arm: 0 }], gross: 100, low: -10, high: 10 },
  ),
  {
    loaded: ["a"],
    stopped: "b",
    limit: "gross",
    mass: 60,
    moment: 0,
    zones: [{ zone: "hold", mass: 60 }],
  },
  "the rating bites before the moment does",
);

assert.deepEqual(
  checkLoadManifest(
    [
      { tag: "a", zone: "tail", mass: 15 },
      { tag: "b", zone: "tail", mass: 10 },
    ],
    { zones: [{ zone: "tail", cap: 500, arm: -5 }], gross: 500, low: -100, high: 100 },
  ),
  {
    loaded: ["a"],
    stopped: "b",
    limit: "moment",
    mass: 15,
    moment: -75,
    zones: [{ zone: "tail", mass: 15 }],
  },
  "the window bites on the low side too",
);

assert.deepEqual(
  checkLoadManifest([{ tag: "a", zone: "z", mass: 50 }], {
    zones: [{ zone: "z", cap: 50, arm: 1 }],
    gross: 50,
    low: 0,
    high: 50,
  }),
  {
    loaded: ["a"],
    stopped: "",
    limit: "",
    mass: 50,
    moment: 50,
    zones: [{ zone: "z", mass: 50 }],
  },
  "sitting exactly on every limit is not a break",
);

assert.deepEqual(
  checkLoadManifest([], plan),
  {
    loaded: [],
    stopped: "",
    limit: "",
    mass: 0,
    moment: 0,
    zones: [
      { zone: "fore", mass: 0 },
      { zone: "mid", mass: 0 },
      { zone: "aft", mass: 0 },
    ],
  },
  "an empty manifest loads nothing and breaks nothing",
);

assert.deepEqual(
  checkLoadManifest(
    [
      { tag: "a", zone: "fore", mass: 40 },
      { tag: "b", zone: "aft", mass: 20 },
      { tag: "c", zone: "mid", mass: 90 },
    ],
    plan,
  ).loaded,
  ["a", "b", "c"],
  "a load inside every limit goes aboard entire",
);

assert.throws(() => checkLoadManifest([], "plan"), Error, "plan must be a record");
assert.throws(
  () => checkLoadManifest([], { zones: [], gross: 10, low: 0, high: 1 }),
  Error,
  "a plan with no zones is rejected",
);
assert.throws(
  () => checkLoadManifest([], { ...plan, zones: [{ zone: "", cap: 5, arm: 1 }] }),
  Error,
  "an empty zone name is rejected",
);
assert.throws(
  () =>
    checkLoadManifest([], {
      ...plan,
      zones: [
        { zone: "twin", cap: 5, arm: 1 },
        { zone: "twin", cap: 6, arm: 2 },
      ],
    }),
  Error,
  "a repeated zone name is rejected",
);
assert.throws(
  () => checkLoadManifest([], { ...plan, zones: [{ zone: "z", cap: 0, arm: 1 }] }),
  Error,
  "a cap of nought is rejected",
);
assert.throws(
  () => checkLoadManifest([], { ...plan, zones: [{ zone: "z", cap: 5, arm: 1.5 }] }),
  Error,
  "a fractional arm is rejected",
);
assert.throws(() => checkLoadManifest([], { ...plan, gross: 0 }), Error, "a gross of nought is rejected");
assert.throws(() => checkLoadManifest([], { ...plan, low: 200 }), Error, "low above high is rejected");
assert.throws(() => checkLoadManifest([], { ...plan, high: "big" }), Error, "high must be a whole number");
assert.throws(() => checkLoadManifest("cargo", plan), Error, "items must be a list");
assert.throws(() => checkLoadManifest([9], plan), Error, "an item must be a record");
assert.throws(
  () => checkLoadManifest([{ tag: "", zone: "mid", mass: 5 }], plan),
  Error,
  "an empty tag is rejected",
);
assert.throws(
  () =>
    checkLoadManifest(
      [
        { tag: "same", zone: "mid", mass: 5 },
        { tag: "same", zone: "mid", mass: 6 },
      ],
      plan,
    ),
  Error,
  "a repeated tag is rejected",
);
assert.throws(
  () => checkLoadManifest([{ tag: "a", zone: "nowhere", mass: 5 }], plan),
  Error,
  "an unknown zone is rejected",
);
assert.throws(
  () => checkLoadManifest([{ tag: "a", zone: "mid", mass: 0 }], plan),
  Error,
  "a mass of nought is rejected",
);
console.log("ok");
