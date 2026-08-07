import assert from "node:assert/strict";
import { dealPacket } from "./solution.ts";

assert.deepEqual(
  dealPacket(["a", "b", "c", "d", "e"], [2, 2], "round"),
  { hands: [["a", "c"], ["b", "d"]], left: ["e"] },
  "what will not fit becomes the leavings",
);
assert.deepEqual(
  dealPacket(["a", "b", "c", "d", "e", "f"], [3, 1, 2], "round"),
  { hands: [["a", "d", "f"], ["b"], ["c", "e"]], left: [] },
  "a hand at its limit is passed over",
);
assert.deepEqual(
  dealPacket(["a", "b", "c", "d", "e", "f", "g"], [2, 2, 2], "snake"),
  { hands: [["a", "f"], ["b", "e"], ["c", "d"]], left: ["g"] },
  "snake calls each end twice",
);
assert.deepEqual(
  dealPacket(["a", "b", "c"], [1, 1], "reverse"),
  { hands: [["b"], ["a"]], left: ["c"] },
  "reverse opens with the last hand",
);
assert.deepEqual(
  dealPacket([], [2], "round"),
  { hands: [[]], left: [] },
  "an empty packet leaves every hand empty",
);
assert.deepEqual(
  dealPacket(["a", "b"], [3], "snake"),
  { hands: [["a", "b"]], left: [] },
  "one hand takes every call",
);
assert.deepEqual(
  dealPacket(["a", "b", "c", "d"], [1, 1, 1], "snake"),
  { hands: [["a"], ["b"], ["c"]], left: ["d"] },
  "limits of one fill on the way up",
);
assert.deepEqual(
  dealPacket(["a", "b", "c", "d", "e"], [4, 1], "reverse"),
  { hands: [["b", "c", "d", "e"], ["a"]], left: [] },
  "one full hand hands every later call to the other",
);
assert.throws(() => dealPacket("abc", [1], "round"), Error, "a packet that is not a list is rejected");
assert.throws(() => dealPacket([""], [1], "round"), Error, "an empty packet entry is rejected");
assert.throws(() => dealPacket([5], [1], "round"), Error, "a non-string packet entry is rejected");
assert.throws(() => dealPacket(["a", "a"], [2], "round"), Error, "a repeated packet entry is rejected");
assert.throws(() => dealPacket(["a"], 2, "round"), Error, "limits that are not a list are rejected");
assert.throws(() => dealPacket(["a"], [], "round"), Error, "an empty list of limits is rejected");
assert.throws(() => dealPacket(["a"], [0], "round"), Error, "a limit of zero is rejected");
assert.throws(() => dealPacket(["a"], [1.5], "round"), Error, "a fractional limit is rejected");
assert.throws(() => dealPacket(["a"], ["2"], "round"), Error, "a limit that is not a number is rejected");
assert.throws(() => dealPacket(["a"], [1], "spiral"), Error, "an unknown turn sequence is rejected");
assert.throws(() => dealPacket(["a"], [1], 3), Error, "a turn sequence that is not a string is rejected");
console.log("ok");
