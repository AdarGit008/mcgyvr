import assert from "node:assert/strict";
import { lastWorkingDays } from "./solution.ts";

assert.deepEqual(
  lastWorkingDays("2026-01", 5),
  ["2026-01-30", "2026-02-27", "2026-03-31", "2026-04-30", "2026-05-29"],
  "early 2026, including a Saturday close and a Sunday close"
);
assert.deepEqual(
  lastWorkingDays("2023-12", 1),
  ["2023-12-29"],
  "December 2023 closes on a Sunday"
);
assert.deepEqual(
  lastWorkingDays("2023-04", 1),
  ["2023-04-28"],
  "April 2023 also closes on a Sunday"
);
assert.deepEqual(
  lastWorkingDays("2023-09", 1),
  ["2023-09-29"],
  "September 2023 closes on a Saturday"
);
assert.deepEqual(
  lastWorkingDays("2024-02", 1),
  ["2024-02-29"],
  "leap February 2024 closes on a Thursday"
);
assert.deepEqual(
  lastWorkingDays("1999-12", 2),
  ["1999-12-31", "2000-01-31"],
  "a run across the millennium boundary"
);
assert.throws(() => lastWorkingDays("2024-2", 1), Error, "unpadded month");
assert.throws(() => lastWorkingDays("2024-00", 1), Error, "month zero");
assert.throws(() => lastWorkingDays("2024-01", 0), Error, "zero count");
assert.throws(() => lastWorkingDays("2024-01", 121), Error, "count beyond cap");
assert.throws(() => lastWorkingDays("9999-12", 2), Error, "run past 9999");
console.log("ok");
