import assert from "node:assert/strict";
import { playDropContest } from "./solution.ts";

assert.deepEqual(
  playDropContest(7, 6, [0, 0, 1, 1, 2, 2, 3]),
  {
    winner: "r",
    played: 7,
    board: [".......", ".......", ".......", ".......", "yyy....", "rrrr..."],
  },
  "four along a row",
);
assert.deepEqual(
  playDropContest(7, 6, [0, 1, 0, 1, 0, 1, 0]),
  {
    winner: "r",
    played: 7,
    board: [".......", ".......", "r......", "ry.....", "ry.....", "ry....."],
  },
  "four down a column",
);
assert.deepEqual(
  playDropContest(7, 6, [0, 1, 1, 2, 6, 2, 2, 3, 6, 3, 6, 3, 3]),
  {
    winner: "r",
    played: 13,
    board: [".......", ".......", "...r...", "..ry..r", ".ryy..r", "ryyy..r"],
  },
  "four on the slant falling to the left",
);
assert.deepEqual(
  playDropContest(7, 6, [6, 5, 5, 4, 0, 4, 4, 3, 0, 3, 0, 3, 3]),
  {
    winner: "r",
    played: 13,
    board: [".......", ".......", "...r...", "r..yr..", "r..yyr.", "r..yyyr"],
  },
  "four on the slant falling to the right",
);
assert.deepEqual(
  playDropContest(7, 6, [0, 0, 1, 1, 2, 2, 3, 4, 5, 6]),
  {
    winner: "r",
    played: 7,
    board: [".......", ".......", ".......", ".......", "yyy....", "rrrr..."],
  },
  "moves after the win are left undropped",
);
assert.deepEqual(
  playDropContest(7, 6, [3, 3, 4, 4, 5, 5, 6]),
  {
    winner: "r",
    played: 7,
    board: [".......", ".......", ".......", ".......", "...yyy.", "...rrrr"],
  },
  "a win against the right-hand wall",
);
assert.deepEqual(
  playDropContest(7, 6, [0, 1, 0, 1]),
  {
    winner: "none",
    played: 4,
    board: [".......", ".......", ".......", ".......", "ry.....", "ry....."],
  },
  "too few discs to win",
);
assert.deepEqual(
  playDropContest(3, 3, [0, 1, 2, 0, 1, 2, 0, 1, 2]),
  { winner: "none", played: 9, board: ["ryr", "yry", "ryr"] },
  "a full board too small to hold four",
);
assert.deepEqual(
  playDropContest(4, 4, []),
  { winner: "none", played: 0, board: ["....", "....", "....", "...."] },
  "no moves at all",
);
assert.deepEqual(
  playDropContest(1, 1, [0]),
  { winner: "none", played: 1, board: ["r"] },
  "a board of one square",
);
assert.throws(
  () => playDropContest(0, 6, []),
  Error,
  "a board with no columns is thrown out",
);
assert.throws(
  () => playDropContest(7, 0, []),
  Error,
  "a board with no rows is thrown out",
);
assert.throws(
  () => playDropContest(7.5, 6, []),
  Error,
  "a side that is not whole is thrown out",
);
assert.throws(
  () => playDropContest(7, 6, "0"),
  Error,
  "moves that are not a list are thrown out",
);
assert.throws(
  () => playDropContest(7, 6, [1.5]),
  Error,
  "a move that is not whole is thrown out",
);
assert.throws(
  () => playDropContest(7, 6, [7]),
  Error,
  "a move past the last column is thrown out",
);
assert.throws(
  () => playDropContest(7, 6, [-1]),
  Error,
  "a move below the first column is thrown out",
);
assert.throws(
  () => playDropContest(1, 2, [0, 0, 0]),
  Error,
  "a move into a full column is thrown out",
);
console.log("ok");
