import assert from "node:assert/strict";
import { readScannedBars } from "./solution.ts";

assert.deepEqual(
  readScannedBars([2, 2, 4, 4, 2, 2, 2, 4, 2]),
  { digits: "0", thin: 2 },
  "the first two places fat name a zero",
);
assert.deepEqual(
  readScannedBars([3, 3, 3, 3, 3, 6, 7, 9, 3]),
  { digits: "9", thin: 3 },
  "fat bars need not measure alike",
);
assert.deepEqual(
  readScannedBars([1, 1, 2, 2, 1, 1, 1, 1, 1, 2, 2, 1, 2, 1]),
  { digits: "07", thin: 1 },
  "two groups read as two digits",
);
assert.deepEqual(
  readScannedBars([4, 4, 4, 8, 4, 8, 4, 8, 4]),
  { digits: "5", thin: 4 },
  "a coarse print reads the same way",
);
assert.deepEqual(
  readScannedBars([2, 2, 2, 5, 2, 5, 2, 2, 5, 2, 5, 2, 2, 5, 2, 5, 2, 5, 2]),
  { digits: "555", thin: 2 },
  "three groups read as three digits",
);
assert.deepEqual(
  readScannedBars([1, 1, 1, 1, 2, 2, 1, 2, 1]),
  { digits: "7", thin: 1 },
  "the thin measure is the least reported anywhere",
);

assert.throws(() => readScannedBars("2,2"), Error, "the sweep must be a list");
assert.throws(() => readScannedBars([1, 1, 1, 1, 1, 1, 1, 1]), Error, "eight bars are too few");
assert.throws(() => readScannedBars([2, 2, 4, 4, 2, 2, 0, 4, 2]), Error, "a measure of zero is rejected");
assert.throws(() => readScannedBars([2, 2, 4, 4, 2, 2, 2.5, 4, 2]), Error, "a fractional measure is rejected");
assert.throws(() => readScannedBars([2, 2, 3, 4, 2, 2, 2, 4, 2]), Error, "a bar on the mark spoils the sweep");
assert.throws(() => readScannedBars([2, 2, 7, 4, 2, 2, 2, 4, 2]), Error, "too fat a bar spoils the sweep");
assert.throws(() => readScannedBars([4, 2, 4, 4, 2, 2, 2, 4, 2]), Error, "a fat opening mark is rejected");
assert.throws(() => readScannedBars([2, 2, 4, 4, 2, 2, 2, 2, 2]), Error, "a thin closing bar pair is rejected");
assert.throws(
  () => readScannedBars([2, 2, 4, 4, 2, 2, 2, 2, 4, 2]),
  Error,
  "six bars between the marks do not divide by five",
);
assert.throws(() => readScannedBars([2, 2, 4, 4, 4, 2, 2, 4, 2]), Error, "three fat bars in a group are rejected");
assert.throws(() => readScannedBars([2, 2, 4, 2, 2, 2, 2, 4, 2]), Error, "one fat bar in a group is rejected");
console.log("ok");
