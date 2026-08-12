import assert from "node:assert/strict";
import { spansOverlap, assignRooms, peakRooms } from "./solution.ts";

assert.deepEqual(assignRooms([]), [], "no meetings, no rooms");
assert.deepEqual(assignRooms([[3, 6]]), [0], "one meeting takes room zero");
assert.deepEqual(assignRooms([[0, 10], [10, 20]]), [0, 0], "touching reuses");
assert.deepEqual(assignRooms([[0, 10], [5, 15]]), [0, 1], "overlap opens a room");
assert.deepEqual(
  assignRooms([[0, 10], [5, 15], [12, 20]]),
  [0, 1, 0],
  "a freed room is reused first",
);
assert.deepEqual(
  assignRooms([[10, 20], [0, 15]]),
  [1, 0],
  "result aligns with input order",
);
assert.deepEqual(
  assignRooms([[5, 30], [5, 10]]),
  [1, 0],
  "start tie is seated by earlier end",
);
assert.deepEqual(
  assignRooms([[3, 6], [3, 6]]),
  [0, 1],
  "identical meetings tie by position",
);
assert.deepEqual(
  assignRooms([[0, 10], [2, 12], [4, 14]]),
  [0, 1, 2],
  "three concurrent meetings",
);
assert.deepEqual(
  assignRooms([[0, 30], [5, 10], [10, 15], [35, 40]]),
  [0, 1, 1, 0],
  "a longer day settles into two rooms",
);
assert.equal(peakRooms([]), 0, "no meetings need no rooms");
assert.equal(peakRooms([[0, 10], [2, 12], [4, 14]]), 3, "peak of three");
assert.equal(peakRooms([[0, 30], [5, 10], [10, 15], [35, 40]]), 2, "peak of two");
assert.equal(spansOverlap([0, 10], [5, 15]), true, "overlapping spans");
assert.equal(spansOverlap([0, 10], [10, 20]), false, "touching spans do not");
assert.throws(() => assignRooms([[5, 2]]), Error, "reversed meeting rejected");
assert.throws(() => assignRooms([[1, 2.5]]), Error, "fractional endpoint");
assert.throws(() => spansOverlap([4, 2], [0, 10]), Error, "reversed span");
console.log("ok");
