import assert from "node:assert/strict";
import { meridianWeekLabel } from "./solution.ts";

assert.equal(meridianWeekLabel("2026-01-07"), "2026-W01", "a week opening on the seventh holds the eighth");
assert.equal(meridianWeekLabel("2026-01-13"), "2026-W01", "the closing Tuesday of week one");
assert.equal(meridianWeekLabel("2026-01-14"), "2026-W02", "the next Wednesday opens week two");
assert.equal(meridianWeekLabel("2026-01-06"), "2025-W52", "the day before week one falls back a year");
assert.equal(meridianWeekLabel("2025-12-31"), "2025-W52", "the tail of December keeps its own year");
assert.equal(meridianWeekLabel("2025-01-01"), "2024-W53", "2024 is a fifty-three week Meridian year");
assert.equal(meridianWeekLabel("2024-02-29"), "2024-W09", "a leap day lands in week nine");
assert.equal(meridianWeekLabel("2027-01-04"), "2026-W52", "a week may spill into the next January");
assert.equal(meridianWeekLabel("2026-12-30"), "2026-W52", "that same spilling week opens in December");
assert.equal(meridianWeekLabel("2020-12-31"), "2020-W52", "an ordinary year closes at week fifty-two");
assert.equal(meridianWeekLabel("2000-01-01"), "1999-W52", "the century turn falls back a year");
assert.equal(meridianWeekLabel("9999-12-31"), "9999-W52", "the top of the permitted span");

assert.throws(() => meridianWeekLabel("2026-1-07"), Error, "an unpadded month is rejected");
assert.throws(() => meridianWeekLabel("2026-01-07 "), Error, "a trailing space is rejected");
assert.throws(() => meridianWeekLabel("0001-06-01"), Error, "a year below the span is rejected");
assert.throws(() => meridianWeekLabel("2026-13-01"), Error, "a month above twelve is rejected");
assert.throws(() => meridianWeekLabel("2026-00-05"), Error, "a month of zero is rejected");
assert.throws(() => meridianWeekLabel("2025-02-29"), Error, "February 29 of a common year is rejected");
assert.throws(() => meridianWeekLabel("2026-04-31"), Error, "a thirty-first of April is rejected");
assert.throws(() => meridianWeekLabel(20260107), Error, "a non-text argument is rejected");
console.log("ok");
