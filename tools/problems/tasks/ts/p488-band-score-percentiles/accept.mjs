import assert from "node:assert/strict";
import { bandScorePercentiles } from "./solution.ts";

const sitters = [
  { tag: "t1", score: 10 },
  { tag: "t2", score: 40 },
  { tag: "t3", score: 40 },
  { tag: "t4", score: 55 },
  { tag: "t5", score: 70 },
  { tag: "t6", score: 70 },
  { tag: "t7", score: 70 },
  { tag: "t8", score: 95 },
];
const cuts = [25, 50, 75];
const names = ["low", "mid", "high", "top"];

const out = bandScorePercentiles(sitters, cuts, names);
assert.deepEqual(
  out.rows,
  [
    { tag: "t1", stand: 0, band: "low" },
    { tag: "t2", stand: 12, band: "low" },
    { tag: "t3", stand: 12, band: "low" },
    { tag: "t4", stand: 37, band: "mid" },
    { tag: "t5", stand: 50, band: "high" },
    { tag: "t6", stand: 50, band: "high" },
    { tag: "t7", stand: 50, band: "high" },
    { tag: "t8", stand: 87, band: "top" },
  ],
  "equal scores share a standing and a standing on a cut takes the band above",
);
assert.deepEqual(
  out.tally,
  [
    { band: "low", count: 3 },
    { band: "mid", count: 1 },
    { band: "high", count: 3 },
    { band: "top", count: 1 },
  ],
  "the tally follows the order the names were listed",
);

assert.deepEqual(
  bandScorePercentiles(
    [
      { tag: "a", score: 1 },
      { tag: "b", score: 2 },
      { tag: "c", score: 3 },
      { tag: "d", score: 4 },
    ],
    [50],
    ["under", "over"],
  ),
  {
    rows: [
      { tag: "a", stand: 0, band: "under" },
      { tag: "b", stand: 25, band: "under" },
      { tag: "c", stand: 50, band: "over" },
      { tag: "d", stand: 75, band: "over" },
    ],
    tally: [
      { band: "under", count: 2 },
      { band: "over", count: 2 },
    ],
  },
  "a single cut splits four sitters in half",
);

assert.deepEqual(
  bandScorePercentiles(
    [
      { tag: "x", score: 8 },
      { tag: "y", score: 8 },
      { tag: "z", score: 8 },
    ],
    [10, 90],
    ["a", "b", "c"],
  ),
  {
    rows: [
      { tag: "x", stand: 0, band: "a" },
      { tag: "y", stand: 0, band: "a" },
      { tag: "z", stand: 0, band: "a" },
    ],
    tally: [
      { band: "a", count: 3 },
      { band: "b", count: 0 },
      { band: "c", count: 0 },
    ],
  },
  "one score for everybody puts everybody in the first band",
);

assert.deepEqual(
  bandScorePercentiles([{ tag: "solo", score: 0 }], [1], ["first", "second"]),
  {
    rows: [{ tag: "solo", stand: 0, band: "first" }],
    tally: [
      { band: "first", count: 1 },
      { band: "second", count: 0 },
    ],
  },
  "one sitter stands at nought",
);

assert.deepEqual(
  bandScorePercentiles(sitters, [1, 99], ["bottom", "middle", "ceiling"]).tally,
  [
    { band: "bottom", count: 1 },
    { band: "middle", count: 7 },
    { band: "ceiling", count: 0 },
  ],
  "wide cuts leave the top band empty",
);

assert.throws(() => bandScorePercentiles("no", cuts, names), Error, "sitters must be a list");
assert.throws(() => bandScorePercentiles([], cuts, names), Error, "an empty roll is rejected");
assert.throws(() => bandScorePercentiles([5], cuts, names), Error, "a sitter must be a record");
assert.throws(
  () => bandScorePercentiles([{ tag: "", score: 4 }], cuts, names),
  Error,
  "an empty tag is rejected",
);
assert.throws(
  () =>
    bandScorePercentiles(
      [
        { tag: "same", score: 4 },
        { tag: "same", score: 5 },
      ],
      cuts,
      names,
    ),
  Error,
  "a repeated tag is rejected",
);
assert.throws(
  () => bandScorePercentiles([{ tag: "a", score: -1 }], cuts, names),
  Error,
  "a negative score is rejected",
);
assert.throws(
  () => bandScorePercentiles([{ tag: "a", score: 4.5 }], cuts, names),
  Error,
  "a fractional score is rejected",
);
assert.throws(() => bandScorePercentiles(sitters, [], []), Error, "an empty cut list is rejected");
assert.throws(
  () => bandScorePercentiles(sitters, [0, 50], ["a", "b", "c"]),
  Error,
  "a cut of nought is rejected",
);
assert.throws(
  () => bandScorePercentiles(sitters, [50, 100], ["a", "b", "c"]),
  Error,
  "a cut of a hundred is rejected",
);
assert.throws(
  () => bandScorePercentiles(sitters, [50, 50], ["a", "b", "c"]),
  Error,
  "cuts that do not rise are rejected",
);
assert.throws(
  () => bandScorePercentiles(sitters, [25, 50], ["a", "b"]),
  Error,
  "too few names are rejected",
);
assert.throws(
  () => bandScorePercentiles(sitters, [25, 50], ["a", "", "c"]),
  Error,
  "an empty name is rejected",
);
assert.throws(
  () => bandScorePercentiles(sitters, [25, 50], ["a", "a", "c"]),
  Error,
  "a repeated name is rejected",
);
console.log("ok");
