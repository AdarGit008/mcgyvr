import assert from "node:assert/strict";
import { carryKittyShares } from "./solution.ts";

assert.deepEqual(
  carryKittyShares([
    { cents: 10, heads: 3 },
    { cents: 0, heads: 2 },
    { cents: 7, heads: 4 },
  ]),
  { each: [3, 0, 2], left: 0 },
  "the odd cent rides on until a later hop can break it up",
);
assert.deepEqual(
  carryKittyShares([
    { cents: 5, heads: 2 },
    { cents: 5, heads: 2 },
  ]),
  { each: [2, 3], left: 0 },
  "a carried cent lifts the next hop's bill",
);
assert.deepEqual(
  carryKittyShares([{ cents: 1, heads: 5 }]),
  { each: [0], left: 1 },
  "a hop too small to split bills nobody and keeps the lot",
);
assert.deepEqual(
  carryKittyShares([{ cents: 99, heads: 1 }]),
  { each: [99], left: 0 },
  "a lone walker is billed the whole hop",
);
assert.deepEqual(
  carryKittyShares([{ cents: 0, heads: 4 }]),
  { each: [0], left: 0 },
  "a free hop bills nothing and keeps nothing",
);
assert.deepEqual(
  carryKittyShares([
    { cents: 8, heads: 3 },
    { cents: 1, heads: 4 },
  ]),
  { each: [2, 0], left: 3 },
  "what the last hop cannot break up is still in the kitty at the end",
);
assert.deepEqual(
  carryKittyShares([
    { cents: 7, heads: 2 },
    { cents: 2, heads: 3 },
  ]),
  { each: [3, 1], left: 0 },
  "the group may shrink or swell between hops",
);

assert.throws(
  () => carryKittyShares([]),
  Error,
  "a journey with no hops is rejected",
);
assert.throws(
  () => carryKittyShares("nope"),
  Error,
  "a non-list argument is rejected",
);
assert.throws(
  () => carryKittyShares([{ cents: 5, heads: 0 }]),
  Error,
  "a hop nobody walked is rejected",
);
assert.throws(
  () => carryKittyShares([{ cents: -5, heads: 2 }]),
  Error,
  "a hop costing less than nothing is rejected",
);
assert.throws(
  () => carryKittyShares([{ cents: 5.5, heads: 2 }]),
  Error,
  "cents that are not whole are rejected",
);
assert.throws(
  () => carryKittyShares([{ cents: 5, heads: 2, tip: 1 }]),
  Error,
  "a hop with a spare key is rejected",
);
assert.throws(
  () => carryKittyShares([{ cents: 5 }]),
  Error,
  "a hop with no head count is rejected",
);
console.log("ok");
