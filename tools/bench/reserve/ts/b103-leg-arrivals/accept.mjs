import assert from "node:assert/strict";
import { parseClock, formatClock, legArrivals } from "./solution.ts";

assert.equal(parseClock("09:05"), 545, "parseClock reads a morning time");
assert.throws(() => parseClock("9:05"), Error, "a one-digit hour is rejected");
assert.equal(formatClock(545), "09:05", "formatClock zero-pads both parts");
assert.throws(() => formatClock(1440), Error, "a full day of minutes is rejected");
assert.deepEqual(legArrivals("10:00", []), [], "no legs, no arrivals");
assert.deepEqual(
  legArrivals("10:00", [[120, 0]]),
  [["12:00", 0]],
  "one leg lands the same day",
);
assert.deepEqual(
  legArrivals("10:00", [[120, 30], [60, 0]]),
  [["12:00", 0], ["13:30", 0]],
  "a layover delays the next leg",
);
assert.deepEqual(
  legArrivals("23:30", [[45, 0]]),
  [["00:15", 1]],
  "a leg across midnight counts a day",
);
assert.deepEqual(
  legArrivals("00:00", [[1440, 0], [1500, 0]]),
  [["00:00", 1], ["01:00", 2]],
  "days accumulate over long legs",
);
assert.deepEqual(
  legArrivals("23:00", [[30, 60], [30, 0]]),
  [["23:30", 0], ["01:00", 1]],
  "a layover can carry the journey past midnight",
);
assert.throws(() => legArrivals("24:00", []), Error, "a bad departure is rejected");
assert.throws(() => legArrivals("10:00", [[30]]), Error, "a one-item leg is rejected");
assert.throws(() => legArrivals("10:00", [[0, 5]]), Error, "zero travel is rejected");
assert.throws(
  () => legArrivals("10:00", [[30, -1]]),
  Error,
  "a negative layover is rejected",
);
console.log("ok");
