import assert from "node:assert/strict";
import { freeWindows } from "./solution.ts";

assert.deepEqual(freeWindows(9, 17, []), [[9, 17]], "untouched window is one gap");
assert.deepEqual(
  freeWindows(9, 17, [[12, 13]]),
  [[9, 12], [13, 17]],
  "one busy interval splits the window",
);
assert.deepEqual(
  freeWindows(0, 100, [[50, 60], [10, 30], [25, 40]]),
  [[0, 10], [40, 50], [60, 100]],
  "unsorted and overlapping busy intervals",
);
assert.deepEqual(
  freeWindows(10, 20, [[0, 12], [18, 25]]),
  [[12, 18]],
  "busy intervals are clipped to the window",
);
assert.deepEqual(
  freeWindows(10, 20, [[0, 5], [30, 40]]),
  [[10, 20]],
  "busy intervals wholly outside are ignored",
);
assert.deepEqual(freeWindows(0, 10, [[0, 10]]), [], "fully booked window");
assert.deepEqual(
  freeWindows(0, 10, [[2, 8], [3, 4]]),
  [[0, 2], [8, 10]],
  "a contained interval adds no gap",
);
assert.deepEqual(
  freeWindows(0, 10, [[2, 4], [4, 6]]),
  [[0, 2], [6, 10]],
  "touching busy intervals leave no gap between them",
);
assert.throws(() => freeWindows(7, 7, []), Error, "empty window is rejected");
assert.throws(() => freeWindows(5, 3, []), Error, "reversed window is rejected");
assert.throws(() => freeWindows(0, 10, [[4, 2]]), Error, "reversed busy interval");
assert.throws(() => freeWindows(0, 10, [[1, 2.5]]), Error, "fractional endpoint");
console.log("ok");
