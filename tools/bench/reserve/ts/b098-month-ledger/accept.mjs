import assert from "node:assert/strict";
import { monthLedger } from "./solution.ts";

assert.deepEqual(
  monthLedger([["2026-03-04", 90]]),
  [["2026-03", 90, 1]],
  "a single entry makes one row",
);
assert.deepEqual(
  monthLedger([["2026-03-04", 90], ["2026-03-11", 30]]),
  [["2026-03", 120, 2]],
  "entries of one month sum",
);
assert.deepEqual(
  monthLedger([["2026-01-05", 10], ["2026-02-06", 20]]),
  [["2026-01", 10, 1], ["2026-02", 20, 1]],
  "neighbouring months stay apart",
);
assert.deepEqual(
  monthLedger([["2026-10-01", 5], ["2026-01-02", 7]]),
  [["2026-01", 7, 1], ["2026-10", 5, 1]],
  "January and October stay apart and sort",
);
assert.deepEqual(
  monthLedger([["2025-12-31", 15], ["2026-01-01", 15]]),
  [["2025-12", 15, 1], ["2026-01", 15, 1]],
  "a year boundary splits rows",
);
assert.deepEqual(
  monthLedger([["2026-06-01", 1], ["2026-04-01", 2], ["2026-06-02", 3]]),
  [["2026-04", 2, 1], ["2026-06", 4, 2]],
  "unordered entries come back sorted",
);
assert.deepEqual(monthLedger([]), [], "no entries means no rows");
assert.throws(() => monthLedger([["2026-3-4", 5]]), Error, "a malformed stamp is rejected");
assert.throws(() => monthLedger([["2026-13-01", 5]]), Error, "month 13 is rejected");
assert.throws(() => monthLedger([["2026-02-00", 5]]), Error, "day zero is rejected");
assert.throws(() => monthLedger([["2026-02-02", 0]]), Error, "zero minutes are rejected");
assert.throws(() => monthLedger([["2026-02-02", 90.5]]), Error, "fractional minutes are rejected");
console.log("ok");
