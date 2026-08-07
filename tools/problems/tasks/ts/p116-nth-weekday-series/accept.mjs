import assert from "node:assert/strict";
import { expandNthWeekday } from "./solution.ts";

assert.deepEqual(
  expandNthWeekday(1, 0, "2000-01", 2),
  ["2000-01-03", "2000-02-07"],
  "first Mondays of Jan and Feb 2000"
);
assert.deepEqual(
  expandNthWeekday(-1, 6, "2000-02", 1),
  ["2000-02-27"],
  "final Sunday of leap February 2000"
);
assert.deepEqual(
  expandNthWeekday(5, 5, "2000-01", 3),
  ["2000-01-29"],
  "only January has a fifth Saturday; Feb and Mar contribute nothing"
);
assert.deepEqual(
  expandNthWeekday(-1, 4, "2026-08", 1),
  ["2026-08-28"],
  "final Friday of August 2026"
);
assert.deepEqual(
  expandNthWeekday(-1, 0, "2024-02", 1),
  ["2024-02-26"],
  "final Monday of leap February 2024"
);
assert.deepEqual(
  expandNthWeekday(1, 6, "1999-12", 2),
  ["1999-12-05", "2000-01-02"],
  "the span crosses a year boundary"
);
assert.deepEqual(
  expandNthWeekday(2, 2, "2026-08", 1),
  ["2026-08-12"],
  "second Wednesday of August 2026"
);
assert.throws(() => expandNthWeekday(0, 0, "2000-01", 1), Error, "ordinal zero");
assert.throws(() => expandNthWeekday(6, 0, "2000-01", 1), Error, "ordinal six");
assert.throws(() => expandNthWeekday(1, 7, "2000-01", 1), Error, "weekday seven");
assert.throws(() => expandNthWeekday(1, 0, "2000-1", 1), Error, "unpadded month");
assert.throws(() => expandNthWeekday(1, 0, "2000-13", 1), Error, "month thirteen");
assert.throws(() => expandNthWeekday(1, 0, "2000-01", 0), Error, "zero months");
assert.throws(() => expandNthWeekday(1, 0, "2000-01", 241), Error, "months beyond cap");
assert.throws(() => expandNthWeekday(1, 0, "9999-12", 2), Error, "span past 9999");
console.log("ok");
