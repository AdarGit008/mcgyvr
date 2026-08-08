import assert from "node:assert/strict";
import { firstRotationBreach } from "./solution.ts";

const permits = [
  ["wheat", "barley"],
  ["wheat", "clover"],
  ["barley", "clover"],
  ["barley", "wheat"],
  ["clover", "wheat"],
  ["clover", "barley"],
  ["clover", "beet"],
  ["beet", "wheat"],
];

assert.equal(
  firstRotationBreach([["wheat", "barley", "clover", "wheat"]], permits),
  "clear",
  "a four-season cycle offends nothing",
);
assert.equal(
  firstRotationBreach([["wheat"], ["beet"]], permits),
  "clear",
  "a single season has nothing behind it to judge",
);
assert.equal(
  firstRotationBreach([["wheat", "beet"]], permits),
  "plot 1 season 2",
  "the table refuses beet behind wheat",
);
assert.equal(
  firstRotationBreach([["wheat", "barley", "wheat"]], permits),
  "plot 1 season 3",
  "wheat returns with only one season between",
);
assert.equal(
  firstRotationBreach([["wheat", "barley", "clover", "barley"]], permits),
  "plot 1 season 4",
  "barley returns with two seasons between",
);
assert.equal(
  firstRotationBreach(
    [
      ["wheat", "barley", "clover", "clover"],
      ["barley", "barley", "wheat", "clover"],
    ],
    permits,
  ),
  "plot 2 season 2",
  "the early breach on the second plot outranks the late one on the first",
);
assert.equal(
  firstRotationBreach(
    [
      ["wheat", "clover", "wheat"],
      ["barley", "clover", "barley"],
    ],
    permits,
  ),
  "plot 1 season 3",
  "when a season holds two breaches the lower plot is named",
);
assert.throws(
  () => firstRotationBreach([], permits),
  Error,
  "an empty record is rejected",
);
assert.throws(
  () => firstRotationBreach("wheat", permits),
  Error,
  "a record that is not a list is rejected",
);
assert.throws(
  () => firstRotationBreach([[]], permits),
  Error,
  "a plot row with no seasons is rejected",
);
assert.throws(
  () => firstRotationBreach([["wheat", "barley"], ["wheat"]], permits),
  Error,
  "rows of unequal length are rejected",
);
assert.throws(
  () => firstRotationBreach([["wheat", ""]], permits),
  Error,
  "a blank crop name is rejected",
);
assert.throws(
  () => firstRotationBreach([["wheat", "barley"]], "wheat"),
  Error,
  "a table that is not a list is rejected",
);
assert.throws(
  () => firstRotationBreach([["wheat", "barley"]], [["wheat"]]),
  Error,
  "a table row that is not a pair is rejected",
);
console.log("ok");
