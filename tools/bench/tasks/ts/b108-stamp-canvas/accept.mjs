import assert from "node:assert/strict";
import { newCanvas, stampRect, inkTotal } from "./solution.ts";

assert.deepEqual(
  newCanvas(2, 3),
  { rows: 2, cols: 3, cells: [[0, 0, 0], [0, 0, 0]] },
  "a fresh canvas is blank",
);
const canvas = newCanvas(2, 3);
assert.equal(stampRect(canvas, [0, 0, 1, 2]), 2, "a stamp reports the cells it inked");
assert.deepEqual(canvas.cells, [[1, 1, 0], [0, 0, 0]], "the stamp landed where aimed");
assert.equal(
  stampRect(canvas, [0, 1, 2, 3]),
  3,
  "an overlapping stamp counts only fresh cells",
);
assert.deepEqual(canvas.cells, [[1, 1, 1], [0, 1, 1]], "overlap never double-marks");
assert.equal(inkTotal(canvas), 5, "the total counts every inked cell");
assert.equal(
  stampRect(canvas, [0, 0, 2, 3]),
  1,
  "a covering stamp finds the last blank cell",
);
assert.equal(stampRect(canvas, [0, 0, 2, 3]), 0, "a stamp over solid ink counts nothing");
assert.throws(() => newCanvas(0, 3), Error, "zero rows are rejected");
assert.throws(() => newCanvas(2, 2.5), Error, "fractional columns are rejected");
assert.throws(() => stampRect(canvas, [1, 0, 1, 3]), Error, "an empty rect is rejected");
assert.throws(
  () => stampRect(canvas, [0, 0, 3, 3]),
  Error,
  "a rect off the canvas is rejected",
);
assert.throws(() => stampRect(canvas, [0, 0, 1]), Error, "a three-bound rect is rejected");
assert.throws(() => stampRect(canvas, [-1, 0, 1, 1]), Error, "a negative top is rejected");
console.log("ok");
