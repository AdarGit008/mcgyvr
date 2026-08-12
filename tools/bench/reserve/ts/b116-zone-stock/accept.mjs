import assert from "node:assert/strict";
import { rackUnits, zoneStock } from "./solution.ts";

const store = {
  name: "dock",
  bins: { bolt: 2 },
  children: [
    {
      name: "north",
      bins: { washer: 5 },
      children: [{ name: "north-1", bins: { bolt: 3 }, children: [] }],
    },
    { name: "annex", bins: { bolt: 1, washer: 2 }, children: [] },
  ],
};

assert.deepEqual(
  zoneStock({ name: "solo", bins: { bolt: 4 }, children: [] }, "bolt"),
  { total: 4, holders: ["solo"] },
  "a lone zone holds its own stock",
);
assert.deepEqual(
  zoneStock(store, "bolt"),
  { total: 6, holders: ["dock", "north-1", "annex"] },
  "holders come in visiting order, each zone before its children",
);
assert.deepEqual(
  zoneStock(store, "washer"),
  { total: 7, holders: ["north", "annex"] },
  "zones without the sku stay out of holders",
);
assert.deepEqual(
  zoneStock(store, "gasket"),
  { total: 0, holders: [] },
  "an unknown sku totals zero",
);
assert.deepEqual(
  zoneStock(
    {
      name: "hub",
      bins: {},
      children: [{ name: "cage", bins: { bolt: 9 }, children: [] }],
    },
    "bolt",
  ),
  { total: 9, holders: ["cage"] },
  "stock deep in one child is found",
);
assert.equal(rackUnits({ bolt: 4 }, "bolt"), 4, "rackUnits reads a listed sku");
assert.equal(rackUnits({ bolt: 4 }, "nut"), 0, "rackUnits reads an absent sku as zero");
assert.throws(
  () =>
    zoneStock(
      {
        name: "dock",
        bins: {},
        children: [{ name: "dock", bins: {}, children: [] }],
      },
      "bolt",
    ),
  Error,
  "one name on two zones is rejected",
);
assert.throws(
  () => zoneStock({ name: "a", bins: { bolt: 0 }, children: [] }, "bolt"),
  Error,
  "a zero count is rejected",
);
assert.throws(
  () => zoneStock({ name: "a", bins: { bolt: 2.5 }, children: [] }, "bolt"),
  Error,
  "a fractional count is rejected",
);
assert.throws(() => zoneStock([], "bolt"), Error, "a zone that is not a record is rejected");
assert.throws(
  () => zoneStock({ bins: {}, children: [] }, "bolt"),
  Error,
  "a missing name is rejected",
);
assert.throws(
  () => zoneStock({ name: "a", bins: 3, children: [] }, "bolt"),
  Error,
  "bins must be a mapping",
);
assert.throws(
  () => zoneStock({ name: "a", bins: {}, children: "none" }, "bolt"),
  Error,
  "children must be a list",
);
assert.throws(() => rackUnits({}, ""), Error, "an empty sku is rejected");
console.log("ok");
