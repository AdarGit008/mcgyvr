import assert from "node:assert/strict";
import { weekdayName } from "./solution.ts";

assert.equal(weekdayName(2024, 1, 1), "Monday", "January date is correct");
assert.equal(weekdayName(2024, 2, 29), "Thursday", "leap-day February is correct");
assert.equal(weekdayName(2000, 1, 1), "Saturday", "century January is correct");
assert.equal(weekdayName(2023, 3, 15), "Wednesday", "March stays correct");
assert.equal(weekdayName(1999, 12, 31), "Friday", "December stays correct");
assert.equal(weekdayName(1776, 7, 4), "Thursday", "eighteenth-century date");
assert.equal(weekdayName(2026, 8, 7), "Friday", "August date stays correct");
assert.throws(() => weekdayName(2024, 13, 1), Error, "month 13 is rejected");
assert.throws(() => weekdayName(2023, 2, 29), Error, "Feb 29 in a common year is rejected");
assert.throws(() => weekdayName(2024, 0, 10), Error, "month 0 is rejected");
assert.throws(() => weekdayName(2024, 4, 31), Error, "April 31 is rejected");
assert.throws(() => weekdayName(0, 5, 5), Error, "year 0 is rejected");
assert.throws(() => weekdayName(2024, 1.5, 1), Error, "fractional month is rejected");
console.log("ok");
