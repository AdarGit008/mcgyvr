import assert from "node:assert/strict";
import { stepAccrualLedger } from "./solution.ts";

assert.deepEqual(
  stepAccrualLedger(100000, [[365, 500, 1]]),
  [[5000, 105000, 0]],
  "one full year, folded in",
);
assert.deepEqual(
  stepAccrualLedger(100000, [
    [365, 500, 1],
    [365, 500, 1],
  ]),
  [
    [5000, 105000, 0],
    [5250, 110250, 0],
  ],
  "the second year earns on the first year's earnings",
);
assert.deepEqual(
  stepAccrualLedger(100000, [
    [365, 500, 0],
    [365, 500, 0],
  ]),
  [
    [5000, 100000, 5000],
    [5000, 100000, 10000],
  ],
  "set aside, the principal never moves",
);
assert.deepEqual(
  stepAccrualLedger(1000000, [
    [1, 100, 0],
    [1, 100, 0],
    [1, 100, 0],
  ]),
  [
    [27, 1000000, 27],
    [27, 1000000, 54],
    [28, 1000000, 82],
  ],
  "the leftover accumulates until it buys a whole cent",
);
assert.deepEqual(
  stepAccrualLedger(200000, [
    [365, 1000, 0],
    [365, 1000, 1],
    [365, 1000, 0],
  ]),
  [
    [20000, 200000, 20000],
    [20000, 220000, 20000],
    [22000, 220000, 42000],
  ],
  "only the folded step lifts later earnings",
);
assert.deepEqual(
  stepAccrualLedger(500000, [[30, 0, 1]]),
  [[0, 500000, 0]],
  "a rate of nothing earns nothing",
);
assert.deepEqual(
  stepAccrualLedger(0, [
    [365, 900, 1],
    [365, 900, 0],
  ]),
  [
    [0, 0, 0],
    [0, 0, 0],
  ],
  "an empty balance earns nothing",
);
assert.throws(
  () => stepAccrualLedger(100000, []),
  Error,
  "an empty schedule is rejected",
);
assert.throws(
  () => stepAccrualLedger(-1, [[365, 500, 1]]),
  Error,
  "a negative opening is rejected",
);
assert.throws(
  () => stepAccrualLedger(100.5, [[365, 500, 1]]),
  Error,
  "a fractional opening is rejected",
);
assert.throws(
  () => stepAccrualLedger(100000, [[365, 500]]),
  Error,
  "a step of two values is rejected",
);
assert.throws(
  () => stepAccrualLedger(100000, [[0, 500, 1]]),
  Error,
  "a step of no days is rejected",
);
assert.throws(
  () => stepAccrualLedger(100000, [[365, -5, 1]]),
  Error,
  "a negative rate is rejected",
);
assert.throws(
  () => stepAccrualLedger(100000, [[365, 500, 2]]),
  Error,
  "a capitalise flag of two is rejected",
);
assert.throws(
  () => stepAccrualLedger(100000, "365,500,1"),
  Error,
  "a schedule that is not a list is rejected",
);
console.log("ok");
