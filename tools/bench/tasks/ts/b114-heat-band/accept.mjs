import assert from "node:assert/strict";
import { runThermostat } from "./solution.ts";

assert.deepEqual(
  runThermostat(18, 15, 20, 3, []),
  { temp: 18, heated: 0, switches: 0, coldest: 18 },
  "no ticks leaves everything at the start",
);
assert.deepEqual(
  runThermostat(20, 10, 30, 5, [-4, 3, -2]),
  { temp: 17, heated: 0, switches: 0, coldest: 16 },
  "inside the band the heater never runs and coldest tracks the dip",
);
assert.deepEqual(
  runThermostat(16, 15, 20, 4, [-3, 0, 0]),
  { temp: 21, heated: 2, switches: 1, coldest: 13 },
  "the heater turns on below low and stays on inside the band",
);
assert.deepEqual(
  runThermostat(16, 15, 20, 4, [-3, 0, 0, 1]),
  { temp: 22, heated: 2, switches: 2, coldest: 13 },
  "reaching high switches the heater off",
);
assert.deepEqual(
  runThermostat(15, 15, 20, 5, [2]),
  { temp: 17, heated: 0, switches: 0, coldest: 15 },
  "exactly low keeps the heater as it was",
);
assert.deepEqual(
  runThermostat(10, 15, 25, 6, [0, 0]),
  { temp: 22, heated: 2, switches: 1, coldest: 10 },
  "a cold start switches on in the first tick",
);
assert.deepEqual(
  runThermostat(14, 15, 17, 3, [0, 0, -5, 0, 0]),
  { temp: 18, heated: 3, switches: 3, coldest: 12 },
  "a second dip starts a second heating cycle",
);
assert.throws(
  () => runThermostat(0.5, 15, 20, 3, []),
  Error,
  "a fractional start is rejected",
);
assert.throws(
  () => runThermostat(18, 15, 20.5, 3, []),
  Error,
  "a fractional high is rejected",
);
assert.throws(
  () => runThermostat(18, 15, 15, 3, []),
  Error,
  "a low meeting high is rejected",
);
assert.throws(
  () => runThermostat(18, 15, 20, 0, []),
  Error,
  "a zero power is rejected",
);
assert.throws(
  () => runThermostat(18, 15, 20, 3, "x"),
  Error,
  "a non-list drifts argument is rejected",
);
assert.throws(
  () => runThermostat(18, 15, 20, 3, [1.5]),
  Error,
  "a fractional drift is rejected",
);
console.log("ok");
