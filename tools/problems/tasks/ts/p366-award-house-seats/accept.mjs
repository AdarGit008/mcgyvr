import assert from "node:assert/strict";
import { awardHouseSeats } from "./solution.ts";

assert.deepEqual(
  awardHouseSeats(
    [
      ["ash", 100],
      ["birch", 80],
      ["cedar", 30],
    ],
    5,
  ),
  { ash: 3, birch: 2 },
  "a roll short of a fifth is struck and never appears",
);

assert.deepEqual(
  awardHouseSeats(
    [
      ["red", 6],
      ["blue", 4],
    ],
    3,
  ),
  { red: 2, blue: 1 },
  "seats alternate as the divisor climbs",
);

assert.deepEqual(
  awardHouseSeats(
    [
      ["big", 10],
      ["small", 10],
    ],
    3,
  ),
  { big: 2, small: 1 },
  "level tallies hand the odd seat to the roll read earlier",
);

assert.deepEqual(
  awardHouseSeats(
    [
      ["low", 6],
      ["high", 12],
    ],
    3,
  ),
  { low: 1, high: 2 },
  "a level quotient goes to the larger tally, not the earlier roll",
);

assert.deepEqual(
  awardHouseSeats(
    [
      ["a", 5],
      ["b", 0],
    ],
    2,
  ),
  { a: 2 },
  "a roll with nothing at all is struck",
);

assert.deepEqual(
  awardHouseSeats([["only", 7]], 4),
  { only: 4 },
  "one standing roll takes every seat",
);

assert.deepEqual(
  awardHouseSeats(
    [
      ["a", 6],
      ["b", 4],
      ["c", 3],
    ],
    1,
  ),
  { a: 1, b: 0, c: 0 },
  "survivors that got nothing still appear with zero",
);

assert.deepEqual(
  awardHouseSeats(
    [
      ["north", 41],
      ["south", 29],
      ["east", 30],
    ],
    7,
  ),
  { north: 3, south: 2, east: 2 },
  "a close three-way house divides by exact quotients",
);

assert.throws(() => awardHouseSeats([], 3), Error, "no rolls at all is rejected");
assert.throws(
  () => awardHouseSeats([["a", 5]], 0),
  Error,
  "a seat count of zero is rejected",
);
assert.throws(
  () => awardHouseSeats([["a", 5]], 2.5),
  Error,
  "a fractional seat count is rejected",
);
assert.throws(
  () => awardHouseSeats([["a", 5, 1]], 2),
  Error,
  "a roll that is not a pair is rejected",
);
assert.throws(
  () =>
    awardHouseSeats(
      [
        ["a", 5],
        ["a", 4],
      ],
      2,
    ),
  Error,
  "two rolls sharing a name are rejected",
);
assert.throws(
  () => awardHouseSeats([["a", -1]], 2),
  Error,
  "a negative tally is rejected",
);
assert.throws(
  () => awardHouseSeats([["a", 0]], 2),
  Error,
  "a house where every tally is zero is rejected",
);
assert.throws(
  () =>
    awardHouseSeats(
      [
        ["a", 1],
        ["b", 1],
        ["c", 1],
        ["d", 1],
        ["e", 1],
        ["f", 1],
      ],
      3,
    ),
  Error,
  "striking every roll is rejected",
);
assert.throws(
  () => awardHouseSeats("rolls", 2),
  Error,
  "rolls that are not a list are rejected",
);
console.log("ok");
