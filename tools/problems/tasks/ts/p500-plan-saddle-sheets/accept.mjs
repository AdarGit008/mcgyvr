import assert from "node:assert/strict";
import { planSaddleSheets } from "./solution.ts";

assert.deepEqual(
  planSaddleSheets(8, "left"),
  ["1 front 8 1", "1 back 2 7", "2 front 6 3", "2 back 4 5"],
  "eight pages fill two sheets exactly",
);

assert.deepEqual(
  planSaddleSheets(4, "left"),
  ["1 front 4 1", "1 back 2 3"],
  "four pages fill one sheet",
);

assert.deepEqual(
  planSaddleSheets(12, "left"),
  [
    "1 front 12 1",
    "1 back 2 11",
    "2 front 10 3",
    "2 back 4 9",
    "3 front 8 5",
    "3 back 6 7",
  ],
  "twelve pages fill three sheets",
);

assert.deepEqual(
  planSaddleSheets(5, "left"),
  ["1 front blank 1", "1 back 2 blank", "2 front blank 3", "2 back 4 5"],
  "five pages pad out to eight",
);

assert.deepEqual(
  planSaddleSheets(6, "left"),
  ["1 front blank 1", "1 back 2 blank", "2 front 6 3", "2 back 4 5"],
  "six pages pad out with two blanks",
);

assert.deepEqual(
  planSaddleSheets(1, "left"),
  ["1 front blank 1", "1 back blank blank"],
  "a single page leaves three blanks",
);

assert.deepEqual(
  planSaddleSheets(8, "right"),
  ["1 front 1 8", "1 back 7 2", "2 front 3 6", "2 back 5 4"],
  "a right binding turns every side about",
);

assert.deepEqual(
  planSaddleSheets(2, "right"),
  ["1 front 1 blank", "1 back blank 2"],
  "a right binding on a padded sheet",
);

assert.throws(() => planSaddleSheets(0, "left"), Error, "no pages at all is refused");
assert.throws(() => planSaddleSheets(4001, "left"), Error, "beyond four thousand is refused");
assert.throws(() => planSaddleSheets(2.5, "left"), Error, "a fractional page count is refused");
assert.throws(() => planSaddleSheets("8", "left"), Error, "a page count that is text is refused");
assert.throws(() => planSaddleSheets(8, "middle"), Error, "an unknown binding is refused");
assert.throws(() => planSaddleSheets(8, 5), Error, "a binding that is not a word is refused");
console.log("ok");
