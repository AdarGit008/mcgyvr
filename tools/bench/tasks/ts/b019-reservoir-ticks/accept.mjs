import assert from "node:assert/strict";
import { runReservoir } from "./solution.ts";

assert.deepEqual(
  runReservoir(10, 4, []),
  { level: 4, spilled: 0, shortfall: 0, served: 0 },
  "no ticks leaves the starting level",
);
assert.deepEqual(
  runReservoir(10, 2, [[5, 0]]),
  { level: 7, spilled: 0, shortfall: 0, served: 0 },
  "inflow within capacity just raises the level",
);
assert.deepEqual(
  runReservoir(10, 8, [[5, 0]]),
  { level: 10, spilled: 3, shortfall: 0, served: 0 },
  "inflow past the brim spills the excess",
);
assert.deepEqual(
  runReservoir(10, 8, [[0, 5]]),
  { level: 3, spilled: 0, shortfall: 0, served: 5 },
  "a covered demand is served in full",
);
assert.deepEqual(
  runReservoir(10, 3, [[0, 7]]),
  { level: 0, spilled: 0, shortfall: 4, served: 3 },
  "an uncovered demand splits into served and shortfall",
);
assert.deepEqual(
  runReservoir(10, 9, [[4, 6]]),
  { level: 4, spilled: 3, shortfall: 0, served: 6 },
  "inflow settles before the same tick's demand draws",
);
assert.deepEqual(
  runReservoir(10, 5, [[5, 0]]),
  { level: 10, spilled: 0, shortfall: 0, served: 0 },
  "filling exactly to the brim spills nothing",
);
assert.deepEqual(
  runReservoir(10, 5, [[0, 5]]),
  { level: 0, spilled: 0, shortfall: 0, served: 5 },
  "draining exactly to empty leaves no shortfall",
);
assert.deepEqual(
  runReservoir(8, 0, [[10, 2], [0, 8], [3, 1]]),
  { level: 2, spilled: 2, shortfall: 2, served: 9 },
  "spill and shortfall accumulate across ticks",
);
assert.deepEqual(
  runReservoir(5, 5, [[0, 0]]),
  { level: 5, spilled: 0, shortfall: 0, served: 0 },
  "a zero-zero tick changes nothing",
);
assert.throws(() => runReservoir(0, 0, []), Error, "zero capacity is rejected");
assert.throws(() => runReservoir(5, 6, []), Error, "start above capacity");
assert.throws(() => runReservoir(10, 5, [[1]]), Error, "a one-item tick");
assert.throws(() => runReservoir(10, 5, [[-1, 0]]), Error, "negative inflow");
assert.throws(() => runReservoir(10, 5, [[0, 1.5]]), Error, "fractional demand");
console.log("ok");
