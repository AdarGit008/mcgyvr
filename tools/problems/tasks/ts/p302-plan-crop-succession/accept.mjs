import assert from "node:assert/strict";
import { planCropSuccession } from "./solution.ts";

const table = [
  ["wheat", "barley"],
  ["wheat", "clover"],
  ["wheat", "beet"],
  ["barley", "clover"],
  ["barley", "beet"],
  ["clover", "wheat"],
  ["clover", "barley"],
  ["beet", "wheat"],
  ["beet", "barley"],
  ["wheat", "fallow"],
];
const ranking = ["clover", "wheat", "barley", "beet", "fallow"];

assert.deepEqual(
  planCropSuccession(["wheat"], table, ranking, 1),
  [["clover"]],
  "one plot takes the highest ranked legal follower",
);
assert.deepEqual(
  planCropSuccession(["wheat"], table, ranking, 3),
  [["clover", "barley", "beet"]],
  "the two-season memory pushes the plot down the ranking",
);
assert.deepEqual(
  planCropSuccession(["wheat", "wheat"], table, ranking, 2),
  [
    ["clover", "barley"],
    ["barley", "clover"],
  ],
  "the allowance of one splits two plots apart",
);
assert.deepEqual(
  planCropSuccession(["wheat", "wheat", "wheat"], table, ranking, 1),
  [["clover"], ["clover"], ["barley"]],
  "three plots allow two of a kind before the allowance bites",
);
assert.deepEqual(
  planCropSuccession(["fallow"], table, ranking, 1),
  [],
  "a crop the table never leads out of collapses the plan",
);
assert.deepEqual(
  planCropSuccession(
    ["rye"],
    [
      ["rye", "oat"],
      ["oat", "rye"],
    ],
    ["rye", "oat"],
    3,
  ),
  [],
  "a two-crop cycle cannot survive the two-season memory",
);
assert.deepEqual(
  planCropSuccession(
    ["rye"],
    [
      ["rye", "oat"],
      ["oat", "rye"],
    ],
    ["rye", "oat"],
    1,
  ),
  [["oat"]],
  "the same cycle plans a single season perfectly well",
);
assert.throws(
  () => planCropSuccession([], table, ranking, 1),
  Error,
  "a farm with no plots is rejected",
);
assert.throws(
  () => planCropSuccession(["wheat", ""], table, ranking, 1),
  Error,
  "a blank plot name is rejected",
);
assert.throws(
  () => planCropSuccession("wheat", table, ranking, 1),
  Error,
  "a plot list that is not a list is rejected",
);
assert.throws(
  () => planCropSuccession(["wheat"], [["wheat", "barley", "beet"]], ranking, 1),
  Error,
  "a table row of three is rejected",
);
assert.throws(
  () =>
    planCropSuccession(
      ["wheat"],
      [
        ["wheat", "barley"],
        ["wheat", "barley"],
      ],
      ranking,
      1,
    ),
  Error,
  "the same pair stated twice is rejected",
);
assert.throws(
  () => planCropSuccession(["wheat"], table, ["clover", "clover"], 1),
  Error,
  "a ranking that repeats a crop is rejected",
);
assert.throws(
  () => planCropSuccession(["wheat"], table, ["clover", "wheat"], 1),
  Error,
  "a table crop missing from the ranking is rejected",
);
assert.throws(
  () => planCropSuccession(["wheat"], table, ranking, 0),
  Error,
  "planning no seasons is rejected",
);
assert.throws(
  () => planCropSuccession(["wheat"], table, ranking, 2.5),
  Error,
  "a fractional season count is rejected",
);
console.log("ok");
