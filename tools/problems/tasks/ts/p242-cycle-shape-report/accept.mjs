import assert from "node:assert/strict";
import { cycleShapeReport } from "./solution.ts";

assert.deepEqual(
  cycleShapeReport([0]),
  { loops: [[0]], widths: [1], repeat: 1, swing: "even" },
  "a single seat handing to itself",
);
assert.deepEqual(
  cycleShapeReport([1, 0]),
  { loops: [[0, 1]], widths: [2], repeat: 2, swing: "odd" },
  "one swap is odd",
);
assert.deepEqual(
  cycleShapeReport([0, 1, 2, 3]),
  { loops: [[0], [1], [2], [3]], widths: [1, 1, 1, 1], repeat: 1, swing: "even" },
  "every seat holds its own baton",
);
assert.deepEqual(
  cycleShapeReport([1, 2, 0, 4, 3]),
  { loops: [[0, 1, 2], [3, 4]], widths: [3, 2], repeat: 6, swing: "odd" },
  "a three-loop beside a two-loop",
);
assert.deepEqual(
  cycleShapeReport([2, 3, 4, 5, 6, 7, 0, 1]),
  {
    loops: [
      [0, 2, 4, 6],
      [1, 3, 5, 7],
    ],
    widths: [4, 4],
    repeat: 4,
    swing: "even",
  },
  "two loops of equal width",
);
assert.deepEqual(
  cycleShapeReport([3, 2, 1, 0]),
  { loops: [[0, 3], [1, 2]], widths: [2, 2], repeat: 2, swing: "even" },
  "loops start at their lowest seat",
);
assert.deepEqual(
  cycleShapeReport([1, 0, 3, 2, 5, 4]),
  { loops: [[0, 1], [2, 3], [4, 5]], widths: [2, 2, 2], repeat: 2, swing: "odd" },
  "three swaps stay odd",
);
assert.deepEqual(
  cycleShapeReport([1, 2, 3, 0, 5, 6, 7, 8, 9, 4]),
  {
    loops: [
      [0, 1, 2, 3],
      [4, 5, 6, 7, 8, 9],
    ],
    widths: [6, 4],
    repeat: 12,
    swing: "even",
  },
  "widths come biggest first and repeat is their least common multiple",
);
assert.throws(() => cycleShapeReport(42), Error, "a non-list is rejected");
assert.throws(() => cycleShapeReport([]), Error, "an empty chart is rejected");
assert.throws(() => cycleShapeReport([1.5, 0]), Error, "a fractional entry is rejected");
assert.throws(() => cycleShapeReport(["0", 1]), Error, "a non-number entry is rejected");
assert.throws(() => cycleShapeReport([1, 2]), Error, "a seat outside the chart is rejected");
assert.throws(() => cycleShapeReport([0, 0]), Error, "a repeated seat is rejected");
console.log("ok");
