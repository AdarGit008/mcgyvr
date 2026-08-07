import assert from "node:assert/strict";
import { shiftLaneLabel } from "./solution.ts";

assert.equal(shiftLaneLabel("A", 1), "B", "one place right of the first lane");
assert.equal(shiftLaneLabel("B", 0), "B", "nought leaves the label alone");
assert.equal(shiftLaneLabel("A", 25), "Z", "twenty-five places reach Z");
assert.equal(shiftLaneLabel("Z", 1), "AA", "past Z the lettering grows");
assert.equal(shiftLaneLabel("A", 26), "AA", "AA is the twenty-seventh lane");
assert.equal(shiftLaneLabel("AA", -1), "Z", "and back again");
assert.equal(shiftLaneLabel("AZ", 1), "BA", "AZ rolls into BA");
assert.equal(shiftLaneLabel("ZZ", 1), "AAA", "ZZ rolls into three capitals");
assert.equal(shiftLaneLabel("AAA", -1), "ZZ", "and back down to two");
assert.equal(shiftLaneLabel("C", -2), "A", "a leftward step reaches the first lane");
assert.equal(shiftLaneLabel("ZZZ", 0), "ZZZ", "the last lane stands still");
assert.equal(shiftLaneLabel("A", 18277), "ZZZ", "the whole board in one step");
assert.throws(
  () => shiftLaneLabel("A", -1),
  Error,
  "there is nothing left of the first lane",
);
assert.throws(
  () => shiftLaneLabel("ZZZ", 1),
  Error,
  "there is nothing right of the last lane",
);
assert.throws(() => shiftLaneLabel("a", 1), Error, "lower case is refused");
assert.throws(() => shiftLaneLabel("", 1), Error, "a blank label is refused");
assert.throws(() => shiftLaneLabel("A1", 1), Error, "a figure is not a capital");
assert.throws(
  () => shiftLaneLabel("AAAA", 0),
  Error,
  "four capitals overrun the board",
);
assert.throws(
  () => shiftLaneLabel("A", 1.5),
  Error,
  "a fractional step is refused",
);
assert.throws(() => shiftLaneLabel(5, 1), Error, "a number is not a label");
console.log("ok");
