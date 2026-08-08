import assert from "node:assert/strict";
import { ferrinWeekSpan } from "./solution.ts";

assert.deepEqual(ferrinWeekSpan(2026, 1), ["2026-01-03", "2026-01-09"], "week one opens on the first Saturday");
assert.deepEqual(ferrinWeekSpan(2026, 0), ["2026-01-01", "2026-01-02"], "the stub week before it");
assert.deepEqual(ferrinWeekSpan(2026, 2), ["2026-01-10", "2026-01-16"], "an ordinary interior week");
assert.deepEqual(ferrinWeekSpan(2026, 52), ["2026-12-26", "2026-12-31"], "the closing week stops at December 31");
assert.deepEqual(ferrinWeekSpan(2024, 0), ["2024-01-01", "2024-01-05"], "a five day stub week");
assert.deepEqual(ferrinWeekSpan(2024, 9), ["2024-03-02", "2024-03-08"], "a leap year week straddling February");
assert.deepEqual(ferrinWeekSpan(2024, 52), ["2024-12-28", "2024-12-31"], "a leap year closing week is clipped too");
assert.deepEqual(ferrinWeekSpan(2022, 1), ["2022-01-01", "2022-01-07"], "a year opening on a Saturday starts at week one");
assert.deepEqual(ferrinWeekSpan(2022, 53), ["2022-12-31", "2022-12-31"], "a closing week of a single day");
assert.deepEqual(ferrinWeekSpan(2021, 52), ["2021-12-25", "2021-12-31"], "a closing week that happens to run the full seven");
assert.deepEqual(ferrinWeekSpan(2000, 1), ["2000-01-01", "2000-01-07"], "a leap century opening on a Saturday");
assert.deepEqual(ferrinWeekSpan(1900, 0), ["1900-01-01", "1900-01-05"], "a common century keeps its stub week");

assert.throws(() => ferrinWeekSpan(2022, 0), Error, "no stub week when the year opens on a Saturday");
assert.throws(() => ferrinWeekSpan(2026, 53), Error, "a week the year never reaches");
assert.throws(() => ferrinWeekSpan(2022, 54), Error, "one past a fifty-three week year");
assert.throws(() => ferrinWeekSpan(2026, -1), Error, "a negative week");
assert.throws(() => ferrinWeekSpan(2026, 1.5), Error, "a fractional week");
assert.throws(() => ferrinWeekSpan(0, 1), Error, "year zero");
assert.throws(() => ferrinWeekSpan(10000, 1), Error, "a year past the ceiling");
assert.throws(() => ferrinWeekSpan("2026", 1), Error, "a year that is not a number");
console.log("ok");
