import assert from "node:assert/strict";
import { walkLadderBoard } from "./solution.ts";

assert.equal(walkLadderBoard(10, [], [8, 3]), 9, "a push past the end is forfeit");
assert.equal(walkLadderBoard(10, [], [7, 4, 2]), 10, "a forfeit does not end the walk");
assert.equal(walkLadderBoard(12, [[4, 9]], [3]), 9, "a mouth carries the counter ahead");
assert.equal(walkLadderBoard(12, [[10, 2]], [9]), 2, "an exit may sit behind its mouth");
assert.equal(walkLadderBoard(5, [[3, 5]], []), 1, "no pushes leaves the counter at the start");
assert.equal(walkLadderBoard(8, [[4, 8]], [3, 2]), 8, "a carry onto the last square finishes");
assert.equal(
  walkLadderBoard(20, [[3, 11], [16, 6], [8, 2]], [2, 5, 2, 3, 16, 15, 4]),
  20,
  "a long track with three chutes",
);
assert.equal(
  walkLadderBoard(20, [[3, 11], [16, 6], [8, 2]], [2, 5, 2, 3]),
  5,
  "the same track stopped before the finish",
);
assert.equal(walkLadderBoard(2, [], [1]), 2, "the shortest legal track");

assert.throws(() => walkLadderBoard(1, [], [1]), Error, "a size under 2 is refused");
assert.throws(() => walkLadderBoard(5.5, [], [1]), Error, "a fractional size is refused");
assert.throws(() => walkLadderBoard(9, [[3, 3]], [1]), Error, "a mouth may not be its own exit");
assert.throws(() => walkLadderBoard(6, [[1, 4]], [1]), Error, "a mouth on square 1 is refused");
assert.throws(() => walkLadderBoard(6, [[6, 2]], [1]), Error, "a mouth on the last square is refused");
assert.throws(() => walkLadderBoard(8, [[3, 5], [3, 6]], [1]), Error, "two chutes sharing a mouth are refused");
assert.throws(() => walkLadderBoard(9, [[3, 5], [5, 7]], [1]), Error, "an exit that is a mouth is refused");
assert.throws(() => walkLadderBoard(9, [[3, 12]], [1]), Error, "a square off the track is refused");
assert.throws(() => walkLadderBoard(9, [[3]], [1]), Error, "a chute that is not a pair is refused");
assert.throws(() => walkLadderBoard(9, [], [0]), Error, "a push of zero is refused");
assert.throws(() => walkLadderBoard(9, [], [2.5]), Error, "a fractional push is refused");
console.log("ok");
