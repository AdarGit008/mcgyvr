import assert from "node:assert/strict";
import { nameStepDistances } from "./solution.ts";

assert.deepEqual(
  nameStepDistances([
    [0, 0],
    [0, 1],
    [0, 2],
    [0, 3],
    [0, 4],
    [0, 5],
    [0, 6],
    [0, 7],
    [0, 8],
    [0, 9],
    [0, 10],
    [0, 11],
  ]),
  {
    names: [
      "unison",
      "minor second",
      "major second",
      "minor third",
      "major third",
      "perfect fourth",
      "tritone",
      "perfect fifth",
      "minor sixth",
      "major sixth",
      "minor seventh",
      "major seventh",
    ],
    lifts: [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    colours: [
      "sweet",
      "sharp",
      "sharp",
      "sweet",
      "sweet",
      "sweet",
      "sharp",
      "sweet",
      "sweet",
      "sweet",
      "sharp",
      "sharp",
    ],
    tally: {
      unison: 1,
      "minor second": 1,
      "major second": 1,
      "minor third": 1,
      "major third": 1,
      "perfect fourth": 1,
      tritone: 1,
      "perfect fifth": 1,
      "minor sixth": 1,
      "major sixth": 1,
      "minor seventh": 1,
      "major seventh": 1,
    },
    widest: 11,
  },
  "every leftover of the table in turn",
);
assert.deepEqual(
  nameStepDistances([
    [60, 60],
    [60, 61],
    [60, 67],
    [60, 72],
    [72, 60],
    [60, 84],
    [60, 79],
    [0, -5],
  ]),
  {
    names: [
      "unison",
      "minor second",
      "perfect fifth",
      "unison",
      "unison",
      "unison",
      "perfect fifth",
      "perfect fourth",
    ],
    lifts: [0, 0, 0, 1, 1, 2, 1, 0],
    colours: ["sweet", "sharp", "sweet", "sweet", "sweet", "sweet", "sweet", "sweet"],
    tally: {
      unison: 4,
      "minor second": 1,
      "perfect fifth": 2,
      "perfect fourth": 1,
    },
    widest: 5,
  },
  "lifts count whole twelves and the order of the marks never matters",
);
assert.deepEqual(
  nameStepDistances([
    [0, 3],
    [10, 13],
  ]),
  {
    names: ["minor third", "minor third"],
    lifts: [0, 0],
    colours: ["sweet", "sweet"],
    tally: { "minor third": 2 },
    widest: 0,
  },
  "the earliest step takes a shared greatest reach",
);
assert.deepEqual(
  nameStepDistances([[-13, -1]]),
  {
    names: ["unison"],
    lifts: [1],
    colours: ["sweet"],
    tally: { unison: 1 },
    widest: 0,
  },
  "negative marks reach just the same",
);
assert.deepEqual(
  nameStepDistances([[0, 25]]),
  {
    names: ["minor second"],
    lifts: [2],
    colours: ["sharp"],
    tally: { "minor second": 1 },
    widest: 0,
  },
  "two whole twelves and one over",
);
assert.throws(() => nameStepDistances(7), Error, "a non-list argument is rejected");
assert.throws(() => nameStepDistances([]), Error, "an empty list of steps is rejected");
assert.throws(() => nameStepDistances([[60]]), Error, "a step of one mark is rejected");
assert.throws(() => nameStepDistances([[60, 61, 62]]), Error, "a step of three marks is rejected");
assert.throws(() => nameStepDistances(["ab"]), Error, "a step that is not a list is rejected");
assert.throws(() => nameStepDistances([["60", 61]]), Error, "a non-number mark is rejected");
assert.throws(() => nameStepDistances([[60, 61.5]]), Error, "a fractional mark is rejected");
console.log("ok");
