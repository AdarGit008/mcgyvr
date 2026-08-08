import assert from "node:assert/strict";
import { orderBoardingBands } from "./solution.ts";

assert.deepEqual(
  orderBoardingBands("ABC|DEF", 10, 3, [
    ["ann", "10A"],
    ["bob", "10C"],
    ["cid", "8F"],
    ["dot", "7B"],
    ["eve", "1D"],
  ]),
  ["ann", "cid", "bob", "dot", "eve"],
  "bands run tail first and windows precede aisles inside a band",
);

assert.deepEqual(
  orderBoardingBands("ABC|DEF", 3, 3, [
    ["p1", "3A"],
    ["p2", "3B"],
    ["p3", "3C"],
    ["p4", "3D"],
    ["p5", "3E"],
    ["p6", "3F"],
  ]),
  ["p1", "p6", "p2", "p5", "p3", "p4"],
  "one row sorts window, middle, aisle and then by layout place",
);

assert.deepEqual(
  orderBoardingBands("ABC|DEF", 5, 5, [
    ["far", "5F"],
    ["near", "5A"],
  ]),
  ["near", "far"],
  "a tie on band, class and row falls to the layout order",
);

assert.deepEqual(
  orderBoardingBands("ABC|DEF", 10, 3, [
    ["front", "7A"],
    ["back", "8C"],
  ]),
  ["back", "front"],
  "an aisle seat in the rear band is called before a window seat ahead of it",
);

assert.deepEqual(
  orderBoardingBands("A|BC", 2, 2, [
    ["mid", "2B"],
    ["nook", "2C"],
    ["odd", "1A"],
  ]),
  ["nook", "odd", "mid"],
  "a one-seat side still yields a window seat at each far end",
);

assert.deepEqual(orderBoardingBands("AB|CD", 4, 2, []), [], "nobody to call");

assert.deepEqual(
  orderBoardingBands("AB|CD", 5, 2, [
    ["q1", "1A"],
    ["q2", "5D"],
    ["q3", "4C"],
  ]),
  ["q2", "q3", "q1"],
  "the frontmost band comes up short and is called last",
);

assert.throws(() => orderBoardingBands(7, 4, 2, []), Error, "the layout must be a string");
assert.throws(() => orderBoardingBands("ABCDEF", 4, 2, []), Error, "no aisle bar is rejected");
assert.throws(() => orderBoardingBands("A|B|C", 4, 2, []), Error, "two aisle bars are rejected");
assert.throws(() => orderBoardingBands("|ABC", 4, 2, []), Error, "an empty side is rejected");
assert.throws(() => orderBoardingBands("Ab|CD", 4, 2, []), Error, "a lowercase letter is rejected");
assert.throws(() => orderBoardingBands("AB|BC", 4, 2, []), Error, "a repeated letter is rejected");
assert.throws(() => orderBoardingBands("AB|CD", 0, 2, []), Error, "a cabin without rows is rejected");
assert.throws(() => orderBoardingBands("AB|CD", 4, 0, []), Error, "a band of no rows is rejected");
assert.throws(() => orderBoardingBands("AB|CD", 4, 2, "x"), Error, "the passengers must be a list");
assert.throws(() => orderBoardingBands("AB|CD", 4, 2, [["solo"]]), Error, "a one-part passenger is rejected");
assert.throws(() => orderBoardingBands("AB|CD", 4, 2, [["", "1A"]]), Error, "an empty name is rejected");
assert.throws(
  () => orderBoardingBands("AB|CD", 4, 2, [["twin", "1A"], ["twin", "2A"]]),
  Error,
  "a shared name is rejected",
);
assert.throws(() => orderBoardingBands("AB|CD", 4, 2, [["x", "A1"]]), Error, "a reversed seat is rejected");
assert.throws(() => orderBoardingBands("AB|CD", 4, 2, [["x", "9A"]]), Error, "a row past the tail is rejected");
assert.throws(() => orderBoardingBands("AB|CD", 4, 2, [["x", "1Z"]]), Error, "an unknown letter is rejected");
assert.throws(
  () => orderBoardingBands("AB|CD", 4, 2, [["x", "2C"], ["y", "2C"]]),
  Error,
  "two passengers in one seat are rejected",
);
console.log("ok");
