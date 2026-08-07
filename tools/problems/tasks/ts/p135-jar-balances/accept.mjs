import assert from "node:assert/strict";
import { jarBalances } from "./solution.ts";

assert.deepEqual(
  jarBalances(10, 100, [3, 4]),
  [7, 13],
  "monthly closes accumulate under a roomy lid",
);
assert.deepEqual(
  jarBalances(10, 5, [0, 0]),
  [5, 5],
  "the spill holds every close at the lid",
);
assert.deepEqual(
  jarBalances(10, 6, [8]),
  [2],
  "spill happens after paying, never before",
);
assert.deepEqual(
  jarBalances(10, 100, [2, 17]),
  [8, 1],
  "last month's remainder helps cover a big outflow",
);
assert.deepEqual(jarBalances(5, 10, [5]), [0], "an exact payout closes at zero");
assert.deepEqual(jarBalances(7, 3, []), [], "no months, no closes");
assert.deepEqual(
  jarBalances(0, 9, [0, 0, 0]),
  [0, 0, 0],
  "a zero topup jar just stays empty",
);
assert.throws(
  () => jarBalances(10, 100, [15]),
  Error,
  "an outflow the jar cannot cover is rejected",
);
assert.throws(
  () => jarBalances(10, 100, [-1]),
  Error,
  "a negative outflow is rejected",
);
assert.throws(
  () => jarBalances(2.5, 100, [1]),
  Error,
  "a fractional topup is rejected",
);
assert.throws(() => jarBalances(10, -3, [1]), Error, "a negative lid is rejected");
assert.throws(
  () => jarBalances(10, 100, "3"),
  Error,
  "a non-list outflows argument is rejected",
);
console.log("ok");
