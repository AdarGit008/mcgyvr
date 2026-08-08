import assert from "node:assert/strict";
import { trimPocketOverflow } from "./solution.ts";

assert.deepEqual(
  trimPocketOverflow([300, 500, 200], 600),
  [300, 300, 0],
  "the crossing entry is cut to the room left, not handed over whole",
);
assert.deepEqual(
  trimPocketOverflow([100, 100], 1000),
  [100, 100],
  "a ceiling nobody reaches changes nothing",
);
assert.deepEqual(trimPocketOverflow([100, 100], 0), [0, 0], "a ceiling of zero hands over nothing");
assert.deepEqual(trimPocketOverflow([], 500), [], "a year with no claims hands over nothing");
assert.deepEqual(trimPocketOverflow([700], 700), [700], "an exact fit is handed over whole");
assert.deepEqual(
  trimPocketOverflow([700, 1], 700),
  [700, 0],
  "the entry behind an exact fit is nothing",
);
assert.deepEqual(
  trimPocketOverflow([0, 0, 900], 400),
  [0, 0, 400],
  "entries of zero leave the room untouched",
);
assert.deepEqual(
  trimPocketOverflow([250, 250, 250], 500),
  [250, 250, 0],
  "two entries may land exactly on the ceiling",
);
assert.deepEqual(
  trimPocketOverflow([9000, 40, 5], 25),
  [25, 0, 0],
  "the very first entry may be the crossing one",
);

assert.throws(() => trimPocketOverflow([10], -1), Error, "a negative ceiling is rejected");
assert.throws(() => trimPocketOverflow([10], 2.5), Error, "a fractional ceiling is rejected");
assert.throws(() => trimPocketOverflow([10], "5"), Error, "a non-numeric ceiling is rejected");
assert.throws(() => trimPocketOverflow([10, -1], 500), Error, "a negative entry is rejected");
assert.throws(() => trimPocketOverflow([1.5], 500), Error, "a fractional entry is rejected");
console.log("ok");
