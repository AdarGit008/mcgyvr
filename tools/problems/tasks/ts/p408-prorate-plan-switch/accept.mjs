import assert from "node:assert/strict";
import { proratePlanSwitch } from "./solution.ts";

assert.deepEqual(
  proratePlanSwitch(30, 16, 3000, 6000),
  { credit: 1500, charge: 3000, due: 1500, carried: 0 },
  "a mid-cycle upgrade over an even split",
);
assert.deepEqual(
  proratePlanSwitch(30, 1, 3000, 6000),
  { credit: 3000, charge: 6000, due: 3000, carried: 0 },
  "moving on the cycle's first day uses every day",
);
assert.deepEqual(
  proratePlanSwitch(30, 30, 3000, 6000),
  { credit: 100, charge: 200, due: 100, carried: 0 },
  "moving on the last day uses one day",
);
assert.deepEqual(
  proratePlanSwitch(31, 11, 6000, 1200),
  { credit: 4064, charge: 813, due: 0, carried: 3251 },
  "a downgrade carries the difference",
);
assert.deepEqual(
  proratePlanSwitch(7, 3, 1000, 1000),
  { credit: 714, charge: 715, due: 1, carried: 0 },
  "the same price still owes a cent, credit down and charge up",
);
assert.deepEqual(
  proratePlanSwitch(28, 8, 5600, 0),
  { credit: 4200, charge: 0, due: 0, carried: 4200 },
  "a free plan carries the whole credit",
);
assert.deepEqual(
  proratePlanSwitch(28, 8, 0, 5600),
  { credit: 0, charge: 4200, due: 4200, carried: 0 },
  "nothing paid means the charge stands alone",
);
assert.deepEqual(
  proratePlanSwitch(1, 1, 999, 999),
  { credit: 999, charge: 999, due: 0, carried: 0 },
  "a one-day cycle matches exactly",
);
assert.deepEqual(
  proratePlanSwitch(10, 5, 0, 0),
  { credit: 0, charge: 0, due: 0, carried: 0 },
  "two free plans settle at nothing",
);

assert.throws(() => proratePlanSwitch(0, 1, 100, 100), Error, "a cycle of no days");
assert.throws(() => proratePlanSwitch(30.5, 1, 100, 100), Error, "a fractional cycle");
assert.throws(() => proratePlanSwitch(30, 0, 100, 100), Error, "a move before the cycle");
assert.throws(() => proratePlanSwitch(30, 31, 100, 100), Error, "a move past the cycle");
assert.throws(() => proratePlanSwitch(30, 2.5, 100, 100), Error, "a fractional day");
assert.throws(() => proratePlanSwitch(30, 5, -1, 100), Error, "a negative amount paid");
assert.throws(() => proratePlanSwitch(30, 5, 100, -1), Error, "a negative plan price");
assert.throws(() => proratePlanSwitch(30, 5, 100.5, 100), Error, "a fractional amount paid");
assert.throws(() => proratePlanSwitch(30, 5, 100, "600"), Error, "a price that is not a number");
console.log("ok");
