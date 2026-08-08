import assert from "node:assert/strict";
import { orderShelfMarks } from "./solution.ts";

assert.deepEqual(
  orderShelfMarks(["QA 76.73 p12", "QA 76.9 p1", "QA 76 z3", "B 5.5 a1"]),
  ["B 5.5 a1", "QA 76 z3", "QA 76.73 p12", "QA 76.9 p1"],
  "stack first, then the run, fractions read as decimals",
);
assert.deepEqual(
  orderShelfMarks(["PR 100 m10", "PR 100 m7", "PR 100 b99"]),
  ["PR 100 b99", "PR 100 m7", "PR 100 m10"],
  "cutter digits are whole numbers, not decimals",
);
assert.deepEqual(
  orderShelfMarks(["AB 1 a1", "A 9 z9", "B 1 a1"]),
  ["A 9 z9", "AB 1 a1", "B 1 a1"],
  "a shorter stack shelves before the longer one it opens",
);
assert.deepEqual(
  orderShelfMarks(["Z 9 a1", "Z 100 a1", "Z 10 a1"]),
  ["Z 9 a1", "Z 10 a1", "Z 100 a1"],
  "runs count, they do not spell",
);
assert.deepEqual(
  orderShelfMarks(["M 3.1 a1", "M 3 a1"]),
  ["M 3 a1", "M 3.1 a1"],
  "a bare run shelves ahead of a fractioned one",
);
assert.deepEqual(
  orderShelfMarks(["QA 1 a1"]),
  ["QA 1 a1"],
  "a batch of one comes back as it went in",
);
assert.deepEqual(
  orderShelfMarks(["TX 714.1234 q9", "TX 714.124 q9"]),
  ["TX 714.1234 q9", "TX 714.124 q9"],
  "four fraction digits against three",
);
assert.throws(() => orderShelfMarks([]), Error, "an empty batch is rejected");
assert.throws(
  () => orderShelfMarks("QA 1 a1"),
  Error,
  "a batch that is not a list is rejected",
);
assert.throws(
  () => orderShelfMarks(["qa 76 p1"]),
  Error,
  "a small-letter stack is rejected",
);
assert.throws(
  () => orderShelfMarks(["QA 076 p1"]),
  Error,
  "a leading zero in the run is rejected",
);
assert.throws(
  () => orderShelfMarks(["QA 76.10 p1"]),
  Error,
  "a fraction finishing on a zero is rejected",
);
assert.throws(
  () => orderShelfMarks(["QA  76 p1"]),
  Error,
  "a doubled space is rejected",
);
assert.throws(
  () => orderShelfMarks(["QA 76 P1"]),
  Error,
  "a capital cutter letter is rejected",
);
assert.throws(
  () => orderShelfMarks(["QA 76 p"]),
  Error,
  "a cutter with no digits is rejected",
);
assert.throws(
  () => orderShelfMarks(["QA 76 p1 2019"]),
  Error,
  "a fourth segment is rejected",
);
assert.throws(
  () => orderShelfMarks(["QA 76 p1", "QA 76 p1"]),
  Error,
  "the same mark twice is rejected",
);
assert.throws(
  () => orderShelfMarks([76]),
  Error,
  "a mark that is not a string is rejected",
);
console.log("ok");
