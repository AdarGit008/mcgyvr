import assert from "node:assert/strict";
import { shiftCivilDate } from "./solution.ts";

assert.equal(shiftCivilDate("2024-02-28", 1), "2024-02-29", "leap year has Feb 29");
assert.equal(shiftCivilDate("2023-02-28", 1), "2023-03-01", "common year skips to March");
assert.equal(shiftCivilDate("1900-02-28", 1), "1900-03-01", "century year is not leap");
assert.equal(shiftCivilDate("2000-02-28", 1), "2000-02-29", "400-year century is leap");
assert.equal(shiftCivilDate("2024-01-01", -1), "2023-12-31", "backward across a year");
assert.equal(shiftCivilDate("2024-12-31", 1), "2025-01-01", "forward across a year");
assert.equal(shiftCivilDate("2024-03-10", 365), "2025-03-10", "a common-year span");
assert.equal(shiftCivilDate("2021-06-15", -500), "2020-02-01", "long negative shift");
assert.equal(shiftCivilDate("0999-12-31", 1), "1000-01-01", "output stays zero-padded");
assert.throws(() => shiftCivilDate("2023-02-29", 1), Error, "Feb 29 off leap is rejected");
assert.throws(() => shiftCivilDate("2024-13-01", 1), Error, "month 13 is rejected");
assert.throws(() => shiftCivilDate("2024-04-31", 0), Error, "April 31 is rejected");
assert.throws(() => shiftCivilDate("2024-1-05", 1), Error, "unpadded month is rejected");
assert.throws(() => shiftCivilDate("2024-06-15", 1.5), Error, "fractional days is rejected");
assert.throws(() => shiftCivilDate("9999-12-31", 1), Error, "result past 9999 is rejected");
console.log("ok");
