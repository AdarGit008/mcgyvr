import assert from "node:assert/strict";
import { raceLadderBoard } from "./solution.ts";

assert.deepEqual(raceLadderBoard(6, [], [["x", 2], ["x", 3]]), { x: 5 }, "one runner, two turns");
assert.deepEqual(
  raceLadderBoard(6, [], [["x", 5], ["x", 3], ["x", 1]]),
  { x: 6 },
  "a forfeit turn leaves the runner in place",
);
assert.deepEqual(raceLadderBoard(5, [], [["z", 9]]), { z: 0 }, "a runner may never leave square 0");
assert.deepEqual(raceLadderBoard(8, [], [["a", 4], ["b", 4]]), { a: 0, b: 4 }, "arriving knocks the sitter back");
assert.deepEqual(
  raceLadderBoard(7, [], [["a", 3], ["b", 3], ["a", 3]]),
  { a: 3, b: 0 },
  "a knocked-back runner may return and knock back in turn",
);
assert.deepEqual(
  raceLadderBoard(10, [[2, 7]], [["a", 7], ["b", 2]]),
  { a: 0, b: 7 },
  "a carried runner clears the exit square it rests on",
);
assert.deepEqual(raceLadderBoard(4, [], [["a", 4], ["a", 1]]), { a: 4 }, "a home runner skips later turns");
assert.deepEqual(raceLadderBoard(9, [[4, 9]], [["a", 4], ["a", 2]]), { a: 9 }, "a chute may carry a runner home");
assert.deepEqual(
  raceLadderBoard(12, [[5, 9], [11, 3]], [
    ["ana", 5],
    ["bo", 9],
    ["ana", 5],
    ["bo", 11],
    ["ana", 3],
    ["ana", 1],
    ["cy", 3],
  ]),
  { ana: 12, bo: 0, cy: 3 },
  "three runners over a lane with two chutes",
);

assert.throws(() => raceLadderBoard(1, [], []), Error, "a size under 2 is refused");
assert.throws(() => raceLadderBoard(3.5, [], []), Error, "a fractional size is refused");
assert.throws(() => raceLadderBoard(8, [[3, 3]], []), Error, "a mouth equal to its exit is refused");
assert.throws(() => raceLadderBoard(8, [[8, 2]], []), Error, "a mouth on the home square is refused");
assert.throws(() => raceLadderBoard(9, [[3, 5], [3, 6]], []), Error, "two chutes sharing a mouth are refused");
assert.throws(() => raceLadderBoard(9, [[3, 5], [5, 7]], []), Error, "an exit that is a mouth is refused");
assert.throws(() => raceLadderBoard(9, [[3, 20]], []), Error, "a chute square off the lane is refused");
assert.throws(() => raceLadderBoard(9, [], [["a"]]), Error, "a turn that is not a pair is refused");
assert.throws(() => raceLadderBoard(9, [], [["", 2]]), Error, "an empty name is refused");
assert.throws(() => raceLadderBoard(9, [], [[7, 2]]), Error, "a non-string name is refused");
assert.throws(() => raceLadderBoard(9, [], [["a", 0]]), Error, "steps of zero are refused");
assert.throws(() => raceLadderBoard(9, [], [["a", 1.5]]), Error, "fractional steps are refused");
console.log("ok");
