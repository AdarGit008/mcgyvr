import assert from "node:assert/strict";
import { judgeLancer } from "./solution.ts";

const board = [
  ".......",
  "..W....",
  ".......",
  "..B.WB.",
  "..W....",
  ".......",
  ".......",
];
const rest = board.slice(2);

assert.equal(judgeLancer(board, "W", [1, 2], [1, 5]), "ok", "a clear three-square slide");
assert.equal(judgeLancer(board, "W", [1, 2], [3, 2]), "ok", "capture at range two");
assert.equal(judgeLancer(board, "B", [3, 2], [1, 2]), "ok", "black captures upward at range two");
assert.equal(
  judgeLancer([".......", "W..B...", ...rest], "W", [1, 0], [1, 3]),
  "ok",
  "capture at full three-square reach",
);
assert.equal(judgeLancer(board, "W", [4, 2], [4, 0]), "ok", "a quiet two-square slide");
assert.equal(judgeLancer(board, "W", [3, 4], [3, 5]), "too_close", "an adjacent enemy cannot be taken");
assert.equal(judgeLancer(board, "B", [3, 5], [3, 3]), "blocked", "sliding across a piece");
assert.equal(judgeLancer(board, "W", [1, 2], [4, 2]), "blocked", "the crossed square is checked, not skipped");
assert.equal(judgeLancer(board, "W", [4, 2], [1, 2]), "blocked", "blocked works in both directions");
assert.equal(
  judgeLancer([".......", "WWW....", ...rest], "W", [1, 0], [1, 2]),
  "blocked",
  "blocked outranks own_piece at the landing",
);
assert.equal(
  judgeLancer([".......", "W.W....", ...rest], "W", [1, 0], [1, 2]),
  "own_piece",
  "landing on one's own lancer",
);
assert.equal(judgeLancer(board, "W", [1, 2], [2, 3]), "bad_line", "no diagonal slides");
assert.equal(judgeLancer(board, "W", [1, 2], [1, 6]), "bad_line", "four squares is too far");
assert.equal(judgeLancer(board, "W", [1, 2], [1, 2]), "bad_line", "standing still is not a move");
assert.equal(judgeLancer(board, "W", [3, 3], [3, 2]), "no_piece", "an empty from square");
assert.equal(judgeLancer(board, "W", [3, 2], [3, 1]), "no_piece", "an enemy lancer is not yours to move");
assert.equal(judgeLancer(board, "W", [1, 2], [-1, 2]), "off_board", "the to square must be on the board");
assert.equal(judgeLancer(board, "W", [7, 2], [6, 2]), "off_board", "off_board outranks no_piece");
assert.throws(() => judgeLancer(board.slice(1), "W", [1, 2], [1, 3]), Error, "six rows are rejected");
assert.throws(
  () => judgeLancer([".......", "..X....", ...rest], "W", [1, 2], [1, 3]),
  Error,
  "a stray character is rejected",
);
assert.throws(() => judgeLancer(board, "w", [1, 2], [1, 3]), Error, "a lowercase side is rejected");
assert.throws(() => judgeLancer(board, "W", [1], [1, 3]), Error, "a one-number square is rejected");
assert.throws(() => judgeLancer(board, "W", [1, 2], [1, 2.5]), Error, "a fractional coordinate is rejected");
console.log("ok");
