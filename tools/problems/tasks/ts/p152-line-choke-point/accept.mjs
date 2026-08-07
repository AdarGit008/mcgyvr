import assert from "node:assert/strict";
import { lineChokePoint } from "./solution.ts";

assert.deepEqual(
  lineChokePoint([["cut", 1, 12], ["weld", 1, 7], ["paint", 1, 9]]),
  { station: "weld", output: 7 },
  "single-machine stations: smallest rate is the choke point",
);
assert.deepEqual(
  lineChokePoint([["cut", 3, 5], ["press", 1, 10]]),
  { station: "press", output: 10 },
  "parallel machines multiply: 3x5=15 beats 1x10 even though 5<10",
);
assert.deepEqual(
  lineChokePoint([["a", 2, 6], ["b", 4, 3], ["c", 1, 12]]),
  { station: "a", output: 12 },
  "three-way capacity tie keeps the earliest station",
);
assert.deepEqual(
  lineChokePoint([["only", 5, 4]]),
  { station: "only", output: 20 },
  "one station is its own choke point",
);
assert.deepEqual(
  lineChokePoint([["fast", 10, 10], ["slow", 2, 2], ["mid", 3, 3]]),
  { station: "slow", output: 4 },
  "capacity is machines times rate at every station",
);
assert.throws(() => lineChokePoint([]), Error, "empty line is rejected");
assert.throws(
  () => lineChokePoint([["a", 0, 5]]),
  Error,
  "zero machines is rejected",
);
assert.throws(
  () => lineChokePoint([["a", 2, 2.5]]),
  Error,
  "fractional rate is rejected",
);
assert.throws(
  () => lineChokePoint([["a", 1, 5], ["a", 2, 9]]),
  Error,
  "duplicate station name is rejected",
);
assert.throws(
  () => lineChokePoint([["", 1, 5]]),
  Error,
  "empty station name is rejected",
);
console.log("ok");
