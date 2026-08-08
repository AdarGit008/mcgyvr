import assert from "node:assert/strict";
import { fitLabelSheet } from "./solution.ts";

const sheet = (width, height, marginX, marginY, gapX, gapY) => ({
  width,
  height,
  marginX,
  marginY,
  gapX,
  gapY,
});
const label = (width, height, turn) => ({ width, height, turn });

assert.deepEqual(
  fitLabelSheet(sheet(210, 297, 10, 10, 0, 0), label(63, 38, false)),
  { across: 3, down: 7, total: 21, turned: false },
  "a plain gapless sheet",
);
assert.deepEqual(
  fitLabelSheet(sheet(100, 100, 5, 5, 2, 2), label(20, 20, false)),
  { across: 4, down: 4, total: 16, turned: false },
  "gaps are demanded between neighbours only, never at the edges",
);
assert.deepEqual(
  fitLabelSheet(sheet(100, 50, 0, 0, 0, 0), label(40, 20, true)),
  { across: 5, down: 1, total: 5, turned: true },
  "laying the label on its side wins when it yields more",
);
assert.deepEqual(
  fitLabelSheet(sheet(40, 40, 0, 0, 0, 0), label(20, 10, true)),
  { across: 2, down: 4, total: 8, turned: false },
  "an equal count keeps the label upright",
);
assert.deepEqual(
  fitLabelSheet(sheet(100, 50, 0, 0, 0, 0), label(40, 20, false)),
  { across: 2, down: 2, total: 4, turned: false },
  "a label forbidden to turn stays upright even when turning would pay",
);
assert.deepEqual(
  fitLabelSheet(sheet(46, 20, 3, 0, 0, 0), label(40, 20, false)),
  { across: 1, down: 1, total: 1, turned: false },
  "a field exactly one label wide holds exactly one",
);
assert.deepEqual(
  fitLabelSheet(sheet(64, 30, 2, 0, 5, 0), label(25, 30, false)),
  { across: 2, down: 1, total: 2, turned: false },
  "the last column pays no trailing gap",
);
assert.throws(
  () => fitLabelSheet(sheet(30, 30, 5, 5, 0, 0), label(25, 25, true)),
  Error,
  "a label wider than the printable field is refused",
);
assert.throws(
  () => fitLabelSheet(sheet(10, 10, 5, 1, 0, 0), label(2, 2, false)),
  Error,
  "margins that swallow the whole width are refused",
);
assert.throws(
  () => fitLabelSheet(sheet(100, 100, 0, 0, 0, 0), label(0, 10, false)),
  Error,
  "a label measurement of zero is rejected",
);
assert.throws(
  () => fitLabelSheet(sheet(100, 100, -1, 0, 0, 0), label(10, 10, false)),
  Error,
  "a negative margin is rejected",
);
assert.throws(
  () => fitLabelSheet(sheet(100, 100, 0, 0, 1.5, 0), label(10, 10, false)),
  Error,
  "a fractional gap is rejected",
);
assert.throws(
  () => fitLabelSheet(sheet(100, 100, 0, 0, 0, 0), { width: 10, height: 10 }),
  Error,
  "a missing turn flag is rejected",
);
console.log("ok");
