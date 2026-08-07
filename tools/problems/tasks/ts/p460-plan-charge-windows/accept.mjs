import assert from "node:assert/strict";
import { planChargeWindows } from "./solution.ts";

const w = (label, opens, shuts, price, rate, blocked = false) => ({ label, opens, shuts, price, rate, blocked });
const night = [w("peak", 0, 4, 30, 5), w("night", 4, 10, 7, 4), w("day", 10, 14, 18, 6)];

assert.deepEqual(
  planChargeWindows(night, 20),
  { plan: [["night", 20]], cost: 140, short: 0 },
  "a target the cheapest window swallows whole leaves the others alone",
);
assert.deepEqual(
  planChargeWindows(night, 30),
  { plan: [["night", 24], ["day", 6]], cost: 276, short: 0 },
  "the overflow goes to the next cheapest window",
);
assert.deepEqual(
  planChargeWindows(night, 100),
  { plan: [["peak", 20], ["night", 24], ["day", 24]], cost: 1200, short: 32 },
  "a target past every window's room leaves a shortfall",
);
assert.deepEqual(
  planChargeWindows(night, 0),
  { plan: [], cost: 0, short: 0 },
  "asking for nothing draws nothing",
);
assert.deepEqual(
  planChargeWindows([w("peak", 0, 4, 30, 5), w("night", 4, 10, 7, 4, true)], 10),
  { plan: [["peak", 10]], cost: 300, short: 0 },
  "a barred window is passed over however cheap it is",
);
assert.deepEqual(
  planChargeWindows([w("late", 8, 10, 5, 3), w("early", 0, 2, 5, 3)], 8),
  { plan: [["early", 6], ["late", 2]], cost: 40, short: 0 },
  "windows at one price are drawn from in clock order",
);
assert.deepEqual(
  planChargeWindows([], 5),
  { plan: [], cost: 0, short: 5 },
  "no windows at all leaves the whole target short",
);
assert.deepEqual(
  planChargeWindows([w("a", 0, 2, 4, 3)], 6),
  { plan: [["a", 6]], cost: 24, short: 0 },
  "a target that fills one window exactly",
);
assert.deepEqual(
  planChargeWindows([w("a", 0, 2, 0, 3), w("b", 2, 4, 9, 3)], 8),
  { plan: [["a", 6], ["b", 2]], cost: 18, short: 0 },
  "a window priced at nothing is drawn on first and adds nothing",
);
assert.deepEqual(
  planChargeWindows([w("a", 0, 5, 2, 1), w("b", 5, 10, 1, 1)], 7),
  { plan: [["a", 2], ["b", 5]], cost: 9, short: 0 },
  "the plan is reported by the clock even when the cheap window comes last",
);

assert.throws(() => planChargeWindows("no", 5), Error, "windows that are not a list are refused");
assert.throws(() => planChargeWindows([], -1), Error, "a negative target is refused");
assert.throws(() => planChargeWindows([], 1.5), Error, "a fractional target is refused");
assert.throws(() => planChargeWindows([[1, 2]], 5), Error, "a window that is not a record is refused");
assert.throws(() => planChargeWindows([w("", 0, 1, 1, 1)], 5), Error, "an empty label is refused");
assert.throws(() => planChargeWindows([w("a", 0, 1, 1, 1), w("a", 2, 3, 1, 1)], 5), Error, "one label twice is refused");
assert.throws(() => planChargeWindows([w("a", -1, 1, 1, 1)], 5), Error, "an opening before nought is refused");
assert.throws(() => planChargeWindows([w("a", 3, 3, 1, 1)], 5), Error, "a window that shuts as it opens is refused");
assert.throws(() => planChargeWindows([w("a", 3, 2, 1, 1)], 5), Error, "a window that shuts before it opens is refused");
assert.throws(() => planChargeWindows([w("a", 0, 1, -1, 1)], 5), Error, "a negative price is refused");
assert.throws(() => planChargeWindows([w("a", 0, 1, 1, 0)], 5), Error, "a rate of nought is refused");
assert.throws(() => planChargeWindows([w("a", 0, 1, 1, 1.5)], 5), Error, "a fractional rate is refused");
assert.throws(() => planChargeWindows([w("a", 0, 1, 1, 1, "no")], 5), Error, "a bar that is not a boolean is refused");
assert.throws(
  () => planChargeWindows([w("a", 0, 5, 1, 1), w("b", 4, 9, 1, 1)], 5),
  Error,
  "two windows sharing time are refused",
);
console.log("ok");
