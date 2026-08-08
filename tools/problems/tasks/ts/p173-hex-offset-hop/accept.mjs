import assert from "node:assert/strict";
import { hopOffsetGrid } from "./solution.ts";

assert.deepEqual(
  hopOffsetGrid([0, 0], ["se", "ne"]),
  { cell: [1, 0], distance: 1 },
  "leaving the shifted row, northeast keeps the column climbing",
);
assert.deepEqual(
  hopOffsetGrid([0, 0], ["se", "nw"]),
  { cell: [0, 0], distance: 0 },
  "southeast then northwest returns to the starting address",
);
assert.deepEqual(
  hopOffsetGrid([0, 0], ["se", "se"]),
  { cell: [1, 2], distance: 2 },
  "two southeast moves cross a shifted row and gain a column",
);
assert.deepEqual(
  hopOffsetGrid([0, 0], ["sw", "sw"]),
  { cell: [-1, 2], distance: 2 },
  "two southwest moves drop one column, not two",
);
assert.deepEqual(
  hopOffsetGrid([0, 0], ["nw", "nw"]),
  { cell: [-1, -2], distance: 2 },
  "rows above the origin shift by the same parity rule",
);
assert.deepEqual(
  hopOffsetGrid([4, -3], ["ne", "ne"]),
  { cell: [5, -5], distance: 2 },
  "a negative odd row shifts exactly as a positive odd row does",
);
assert.deepEqual(
  hopOffsetGrid([2, 3], ["e", "w", "ne", "sw"]),
  { cell: [2, 3], distance: 0 },
  "a walk that returns home reports no distance at all",
);
assert.deepEqual(
  hopOffsetGrid([7, -2], []),
  { cell: [7, -2], distance: 0 },
  "an empty move list ends where it began",
);
assert.deepEqual(
  hopOffsetGrid([0, 0], ["e", "e", "se"]),
  { cell: [2, 1], distance: 3 },
  "three moves that never double back stay three apart",
);
assert.deepEqual(
  hopOffsetGrid([0, 0], ["w", "sw", "sw", "e"]),
  { cell: [-1, 2], distance: 2 },
  "four moves can leave only two hops between the ends",
);

assert.throws(() => hopOffsetGrid([0, 0], ["up"]), Error, "an unknown move is rejected");
assert.throws(() => hopOffsetGrid([0, 0], ["NE"]), Error, "an upper-case move is rejected");
assert.throws(() => hopOffsetGrid([0], ["e"]), Error, "a one-element start is rejected");
assert.throws(() => hopOffsetGrid([0, 0.5], ["e"]), Error, "a fractional row is rejected");
assert.throws(() => hopOffsetGrid("00", ["e"]), Error, "a non-address start is rejected");
assert.throws(() => hopOffsetGrid([0, 0], "e"), Error, "a non-list move list is rejected");
console.log("ok");
