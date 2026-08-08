import assert from "node:assert/strict";
import { buildReplenishmentPlan } from "./solution.ts";

assert.deepEqual(
  buildReplenishmentPlan(
    { held: 10, floor: 4, ceiling: 20, pack: 5, lead: 2, inbound: [] },
    [3, 3, 3, 3, 3],
  ),
  { orders: [{ week: 2, units: 20 }], missed: 0, closing: 15 },
  "a steady draw trips the floor once and lands two weeks later",
);

assert.deepEqual(
  buildReplenishmentPlan(
    { held: 2, floor: 0, ceiling: 6, pack: 1, lead: 3, inbound: [] },
    [5, 1, 1, 1],
  ),
  { orders: [{ week: 1, units: 6 }], missed: 5, closing: 5 },
  "a long lead leaves the depot missing draws week after week",
);

assert.deepEqual(
  buildReplenishmentPlan(
    {
      held: 0,
      floor: 2,
      ceiling: 10,
      pack: 4,
      lead: 1,
      inbound: [{ week: 2, units: 8 }],
    },
    [0, 0, 5],
  ),
  { orders: [], missed: 0, closing: 3 },
  "a purchase already made holds the cover up before it lands",
);

assert.deepEqual(
  buildReplenishmentPlan(
    { held: 5, floor: 5, ceiling: 9, pack: 1, lead: 4, inbound: [] },
    [0],
  ),
  { orders: [{ week: 1, units: 4 }], missed: 0, closing: 5 },
  "a purchase landing past the end of the run is still made",
);

assert.deepEqual(
  buildReplenishmentPlan(
    { held: 0, floor: 0, ceiling: 7, pack: 3, lead: 1, inbound: [] },
    [0, 0, 0],
  ),
  { orders: [{ week: 1, units: 9 }], missed: 0, closing: 9 },
  "a want of seven against a pack of three buys nine",
);

assert.deepEqual(
  buildReplenishmentPlan(
    { held: 3, floor: 9, ceiling: 9, pack: 1, lead: 1, inbound: [] },
    [],
  ),
  { orders: [], missed: 0, closing: 3 },
  "a run of no weeks buys nothing at all",
);

assert.deepEqual(
  buildReplenishmentPlan(
    { held: 5, floor: 5, ceiling: 5, pack: 2, lead: 1, inbound: [] },
    [0],
  ),
  { orders: [], missed: 0, closing: 5 },
  "sitting on the floor with nothing wanted buys nothing",
);

assert.deepEqual(
  buildReplenishmentPlan(
    { held: 0, floor: 0, ceiling: 2, pack: 1, lead: 1, inbound: [] },
    [0, 3, 0, 0],
  ),
  {
    orders: [
      { week: 1, units: 2 },
      { week: 2, units: 2 },
    ],
    missed: 1,
    closing: 2,
  },
  "a run may buy more than once and still miss a draw",
);

const sound = { held: 1, floor: 1, ceiling: 2, pack: 1, lead: 1, inbound: [] };
assert.throws(
  () => buildReplenishmentPlan([1, 2], [0]),
  Error,
  "an item that is not a mapping is rejected",
);
assert.throws(
  () => buildReplenishmentPlan({ held: 1, floor: 1, ceiling: 2, pack: 1 }, [0]),
  Error,
  "an item missing keys is rejected",
);
assert.throws(
  () => buildReplenishmentPlan({ ...sound, held: -1 }, [0]),
  Error,
  "a held below nought is rejected",
);
assert.throws(
  () => buildReplenishmentPlan({ ...sound, floor: 5, ceiling: 4 }, [0]),
  Error,
  "a ceiling below the floor is rejected",
);
assert.throws(
  () => buildReplenishmentPlan({ ...sound, pack: 0 }, [0]),
  Error,
  "a pack below one is rejected",
);
assert.throws(
  () => buildReplenishmentPlan({ ...sound, lead: 0 }, [0]),
  Error,
  "a lead below one is rejected",
);
assert.throws(
  () => buildReplenishmentPlan({ ...sound, inbound: "none" }, [0]),
  Error,
  "an inbound that is not a list is rejected",
);
assert.throws(
  () => buildReplenishmentPlan({ ...sound, inbound: [[2, 8]] }, [0]),
  Error,
  "an inbound entry that is not a mapping is rejected",
);
assert.throws(
  () => buildReplenishmentPlan({ ...sound, inbound: [{ week: 2 }] }, [0]),
  Error,
  "an inbound entry missing its units is rejected",
);
assert.throws(
  () => buildReplenishmentPlan({ ...sound, inbound: [{ week: 0, units: 8 }] }, [0]),
  Error,
  "an inbound week below one is rejected",
);
assert.throws(
  () =>
    buildReplenishmentPlan(
      {
        ...sound,
        inbound: [
          { week: 3, units: 8 },
          { week: 3, units: 1 },
        ],
      },
      [0],
    ),
  Error,
  "inbound weeks that do not climb are rejected",
);
assert.throws(
  () => buildReplenishmentPlan(sound, "0"),
  Error,
  "a draws argument that is not a list is rejected",
);
assert.throws(
  () => buildReplenishmentPlan(sound, [-1]),
  Error,
  "a draw below nought is rejected",
);
assert.throws(
  () => buildReplenishmentPlan(sound, [1.5]),
  Error,
  "a draw that is not whole is rejected",
);
console.log("ok");
