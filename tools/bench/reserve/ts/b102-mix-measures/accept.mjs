import assert from "node:assert/strict";
import { combineMeasures } from "./solution.ts";

assert.deepEqual(combineMeasures([], [1, 1]), [], "no pours, no totals");
assert.deepEqual(
  combineMeasures([["milk", 2, 4]], [1, 1]),
  [["milk", 1, 2]],
  "a single pour reduces to lowest terms",
);
assert.deepEqual(
  combineMeasures([["oil", 1, 3], ["oil", 1, 6]], [1, 1]),
  [["oil", 1, 2]],
  "pours of one name total exactly",
);
assert.deepEqual(
  combineMeasures([["basil", 1, 2], ["anise", 1, 2]], [1, 1]),
  [["anise", 1, 2], ["basil", 1, 2]],
  "names come back in ascending order",
);
assert.deepEqual(
  combineMeasures([["stock", 1, 2], ["stock", -1, 2]], [1, 1]),
  [["stock", 0, 1]],
  "a cancelled total reads 0 over 1",
);
assert.deepEqual(
  combineMeasures([["flour", 1, 2]], [3, 2]),
  [["flour", 3, 4]],
  "the batch factor scales the total",
);
assert.deepEqual(
  combineMeasures([["rice", 1, 6], ["rice", 1, 6], ["salt", 1, 1]], [1, 2]),
  [["rice", 1, 6], ["salt", 1, 2]],
  "totals reduce again after scaling",
);
assert.throws(() => combineMeasures("milk", [1, 1]), Error, "a non-list pour list");
assert.throws(
  () => combineMeasures([["milk", 1]], [1, 1]),
  Error,
  "a two-item entry is rejected",
);
assert.throws(
  () => combineMeasures([["", 1, 2]], [1, 1]),
  Error,
  "an empty name is rejected",
);
assert.throws(
  () => combineMeasures([["milk", 1.5, 2]], [1, 1]),
  Error,
  "a fractional numerator is rejected",
);
assert.throws(
  () => combineMeasures([["milk", 1, 0]], [1, 1]),
  Error,
  "a zero denominator is rejected",
);
assert.throws(
  () => combineMeasures([["milk", 1, 2]], [1]),
  Error,
  "a one-part factor is rejected",
);
assert.throws(
  () => combineMeasures([["milk", 1, 2]], [0, 2]),
  Error,
  "a non-positive factor part is rejected",
);
console.log("ok");
