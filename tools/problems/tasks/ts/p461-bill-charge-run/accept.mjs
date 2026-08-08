import assert from "node:assert/strict";
import { billChargeRun } from "./solution.ts";

assert.deepEqual(
  billChargeRun([10, 2, 5, 2], 3, 7),
  { slots: [1, 2, 3], units: 7, bill: 17, short: 0 },
  "the last slot draws only the remainder that is wanted",
);
assert.deepEqual(
  billChargeRun([10, 2, 5, 2], 3, 6),
  { slots: [1, 3], units: 6, bill: 12, short: 0 },
  "a target that lands on a slot boundary uses whole slots",
);
assert.deepEqual(
  billChargeRun([10, 2, 5, 2], 3, 0),
  { slots: [], units: 0, bill: 0, short: 0 },
  "a target of nothing runs the meter in no slot at all",
);
assert.deepEqual(
  billChargeRun([10, 2, 5, 2], 3, 100),
  { slots: [0, 1, 2, 3], units: 12, bill: 57, short: 88 },
  "a target past the whole strip runs everywhere and reports the shortfall",
);
assert.deepEqual(
  billChargeRun([4, 1], 5, 1),
  { slots: [1], units: 1, bill: 1, short: 0 },
  "one unit wanted is billed as one unit, not as a whole slot",
);
assert.deepEqual(
  billChargeRun([], 3, 5),
  { slots: [], units: 0, bill: 0, short: 5 },
  "an empty strip leaves the whole target unmet",
);
assert.deepEqual(
  billChargeRun([3, 3, 3], 2, 3),
  { slots: [0, 1], units: 3, bill: 9, short: 0 },
  "slots at one price are used earliest first",
);
assert.deepEqual(
  billChargeRun([0, 5], 4, 6),
  { slots: [0, 1], units: 6, bill: 10, short: 0 },
  "a slot priced at nothing is used first and adds nothing to the bill",
);
assert.deepEqual(
  billChargeRun([7], 1, 1),
  { slots: [0], units: 1, bill: 7, short: 0 },
  "a strip of one slot met exactly",
);

assert.throws(() => billChargeRun("no", 1, 1), Error, "a strip that is not a list is refused");
assert.throws(() => billChargeRun([-1], 1, 1), Error, "a negative price is refused");
assert.throws(() => billChargeRun([1.5], 1, 1), Error, "a fractional price is refused");
assert.throws(() => billChargeRun(["3"], 1, 1), Error, "a price that is not a number is refused");
assert.throws(() => billChargeRun([1], 0, 1), Error, "a draw of nought is refused");
assert.throws(() => billChargeRun([1], -2, 1), Error, "a negative draw is refused");
assert.throws(() => billChargeRun([1], 1.5, 1), Error, "a fractional draw is refused");
assert.throws(() => billChargeRun([1], 1, -1), Error, "a negative target is refused");
assert.throws(() => billChargeRun([1], 1, 2.5), Error, "a fractional target is refused");
console.log("ok");
