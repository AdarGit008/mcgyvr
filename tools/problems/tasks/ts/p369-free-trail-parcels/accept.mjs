import assert from "node:assert/strict";
import { freeTrailParcels } from "./solution.ts";

assert.deepEqual(
  freeTrailParcels(3, ["LL"]),
  ["LR", "R"],
  "the sibling of an issued parcel stands, and the far half folds up whole",
);
assert.deepEqual(
  freeTrailParcels(3, []),
  [""],
  "an estate with nothing issued is one free parcel, the empty run",
);
assert.deepEqual(
  freeTrailParcels(3, [""]),
  [],
  "issuing the empty run leaves nothing at all",
);
assert.deepEqual(
  freeTrailParcels(2, ["LL", "LR", "RL"]),
  ["RR"],
  "a parent both of whose halves are issued is not free itself",
);
assert.deepEqual(
  freeTrailParcels(3, ["LLL"]),
  ["LLR", "LR", "R"],
  "the free remainder climbs back up one level at a time",
);
assert.deepEqual(
  freeTrailParcels(1, ["L"]),
  ["R"],
  "the shallowest estate has just the one sibling left",
);
assert.deepEqual(
  freeTrailParcels(3, ["R", "LL"]),
  ["LR"],
  "two issued parcels at different depths leave a single gap",
);
assert.deepEqual(
  freeTrailParcels(4, ["LLL", "LR", "RRRR"]),
  ["LLR", "RL", "RRL", "RRRL"],
  "the report runs from the first address held to the last",
);

assert.throws(
  () => freeTrailParcels(0, []),
  Error,
  "a depth below one is rejected",
);
assert.throws(
  () => freeTrailParcels(9, []),
  Error,
  "a depth past eight is rejected",
);
assert.throws(
  () => freeTrailParcels(2.5, []),
  Error,
  "a fractional depth is rejected",
);
assert.throws(
  () => freeTrailParcels(3, ["LX"]),
  Error,
  "a letter outside L and R is rejected",
);
assert.throws(
  () => freeTrailParcels(2, ["LLL"]),
  Error,
  "a parcel longer than the depth is rejected",
);
assert.throws(
  () => freeTrailParcels(3, ["L", "LL"]),
  Error,
  "an issued parcel holding another is rejected",
);
assert.throws(
  () => freeTrailParcels(3, ["LR", "LR"]),
  Error,
  "the same parcel issued twice is rejected",
);
assert.throws(
  () => freeTrailParcels(3, [7]),
  Error,
  "a parcel that is not a string is rejected",
);
assert.throws(
  () => freeTrailParcels(3, "LL"),
  Error,
  "issued parcels that are not a list are rejected",
);
console.log("ok");
