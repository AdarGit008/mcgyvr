import assert from "node:assert/strict";
import { backoffSchedule } from "./solution.ts";

assert.deepEqual(
  backoffSchedule(100, 2, 800, 6),
  [0, 100, 300, 700, 1500, 2300],
  "the idle doubles until it meets the ceiling, then holds there",
);
assert.deepEqual(
  backoffSchedule(5, 1, 5, 4),
  [0, 5, 10, 15],
  "a factor of one gives an evenly spaced schedule",
);
assert.deepEqual(backoffSchedule(9, 4, 9, 1), [0], "one attempt dials at moment zero");
assert.deepEqual(
  backoffSchedule(3, 3, 100, 5),
  [0, 3, 12, 39, 120],
  "an uncapped run tracks the widening idle exactly",
);
assert.deepEqual(
  backoffSchedule(2, 2, 2, 4),
  [0, 2, 4, 6],
  "a ceiling equal to base pins every idle at base",
);
assert.deepEqual(
  backoffSchedule(1, 10, 1000, 6),
  [0, 1, 11, 111, 1111, 2111],
  "a tenfold factor reaches the ceiling on the fourth idle",
);
assert.deepEqual(
  backoffSchedule(250, 2, 3000, 8),
  [0, 250, 750, 1750, 3750, 6750, 9750, 12750],
  "an idle that would overshoot the ceiling is clipped to it",
);
assert.deepEqual(
  backoffSchedule(7, 5, 40, 5),
  [0, 7, 42, 82, 122],
  "the first idle past the ceiling is the ceiling, not the overshoot",
);
assert.equal(backoffSchedule(4, 2, 64, 12).length, 12, "the schedule is as long as asked");

assert.throws(() => backoffSchedule(0, 2, 10, 3), Error, "a base of zero is rejected");
assert.throws(() => backoffSchedule(10, 0, 100, 3), Error, "a factor of zero is rejected");
assert.throws(() => backoffSchedule(10, 2, 9, 3), Error, "a ceiling under base is rejected");
assert.throws(() => backoffSchedule(10, 2, 100, 0), Error, "zero attempts are rejected");
assert.throws(() => backoffSchedule(1.5, 2, 100, 3), Error, "a fractional base is rejected");
assert.throws(() => backoffSchedule(10, 2, 100, true), Error, "a boolean count is rejected");
assert.throws(() => backoffSchedule("10", 2, 100, 3), Error, "a base given as text is rejected");
console.log("ok");
