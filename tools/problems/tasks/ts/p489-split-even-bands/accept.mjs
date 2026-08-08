import assert from "node:assert/strict";
import { splitEvenBands } from "./solution.ts";

const league = [
  { who: "a", mark: 90 },
  { who: "b", mark: 80 },
  { who: "c", mark: 80 },
  { who: "d", mark: 80 },
  { who: "e", mark: 50 },
  { who: "f", mark: 10 },
];

assert.deepEqual(
  splitEvenBands(league, 3),
  [
    { who: "a", band: 1 },
    { who: "b", band: 1 },
    { who: "c", band: 1 },
    { who: "d", band: 1 },
    { who: "e", band: 3 },
    { who: "f", band: 3 },
  ],
  "a tie drags its whole group into the lowest band any of them was handed",
);

assert.deepEqual(
  splitEvenBands(
    [
      { who: "p", mark: 40 },
      { who: "q", mark: 30 },
      { who: "r", mark: 20 },
      { who: "s", mark: 10 },
    ],
    2,
  ),
  [
    { who: "p", band: 1 },
    { who: "q", band: 1 },
    { who: "r", band: 2 },
    { who: "s", band: 2 },
  ],
  "four members with no ties split cleanly in two",
);

assert.deepEqual(
  splitEvenBands(league, 1),
  league.map((member) => ({ who: member.who, band: 1 })),
  "one band holds everybody",
);

assert.deepEqual(
  splitEvenBands(
    [
      { who: "zed", mark: 5 },
      { who: "ash", mark: 5 },
      { who: "moe", mark: 9 },
    ],
    3,
  ),
  [
    { who: "zed", band: 2 },
    { who: "ash", band: 2 },
    { who: "moe", band: 1 },
  ],
  "a tie is settled by the name and then bound together again",
);

assert.deepEqual(
  splitEvenBands(
    [
      { who: "one", mark: 7 },
      { who: "two", mark: 3 },
      { who: "six", mark: 0 },
    ],
    3,
  ),
  [
    { who: "one", band: 1 },
    { who: "two", band: 2 },
    { who: "six", band: 3 },
  ],
  "as many bands as members gives each its own",
);

assert.deepEqual(
  splitEvenBands([{ who: "solo", mark: 0 }], 1),
  [{ who: "solo", band: 1 }],
  "one member fills the only band",
);

assert.throws(() => splitEvenBands("league", 2), Error, "entries must be a list");
assert.throws(() => splitEvenBands([], 1), Error, "an empty league is rejected");
assert.throws(() => splitEvenBands(["a"], 1), Error, "an entry must be a record");
assert.throws(
  () => splitEvenBands([{ who: "", mark: 4 }], 1),
  Error,
  "an empty who is rejected",
);
assert.throws(
  () =>
    splitEvenBands(
      [
        { who: "twin", mark: 4 },
        { who: "twin", mark: 5 },
      ],
      1,
    ),
  Error,
  "a repeated who is rejected",
);
assert.throws(
  () => splitEvenBands([{ who: "a", mark: -3 }], 1),
  Error,
  "a negative mark is rejected",
);
assert.throws(
  () => splitEvenBands([{ who: "a", mark: 1.5 }], 1),
  Error,
  "a fractional mark is rejected",
);
assert.throws(() => splitEvenBands(league, 0), Error, "a band count of nought is rejected");
assert.throws(() => splitEvenBands(league, 7), Error, "more bands than members is rejected");
assert.throws(() => splitEvenBands(league, 2.5), Error, "a fractional band count is rejected");
console.log("ok");
