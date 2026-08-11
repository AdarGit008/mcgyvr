import assert from "node:assert/strict";
import { billedAirtime } from "./solution.ts";

assert.equal(billedAirtime(0, 30, 6), 0, "a zero-second call bills nothing");
assert.equal(billedAirtime(1, 30, 6), 30, "a short call bills the whole initial block");
assert.equal(billedAirtime(30, 30, 6), 30, "the initial boundary bills exactly itself");
assert.equal(billedAirtime(31, 30, 6), 36, "one second past the block starts a step");
assert.equal(billedAirtime(42, 30, 6), 42, "a step boundary bills exactly itself");
assert.equal(billedAirtime(61, 60, 10), 70, "another tariff bills its own steps");
assert.throws(() => billedAirtime(-1, 30, 6), Error, "negative duration is rejected");
assert.throws(() => billedAirtime(10.5, 30, 6), Error, "fractional duration is rejected");
assert.throws(() => billedAirtime(10, 0, 6), Error, "zero initial block is rejected");
assert.throws(() => billedAirtime(10, 30, 0), Error, "zero step is rejected");
console.log("ok");
