import assert from "node:assert/strict";
import { parseDuration } from "./solution.ts";

assert.equal(parseDuration("90s"), 90, "seconds only");
assert.equal(parseDuration("2h"), 7200, "single unit");
assert.equal(parseDuration("1h30m"), 5400, "two units");
assert.equal(parseDuration("1d2h3m4s"), 93784, "all four units");
assert.equal(parseDuration("0s"), 0, "zero is zero");
assert.equal(parseDuration("10m30s"), 630, "minutes and seconds");
assert.throws(() => parseDuration(""), Error, "empty string is rejected");
assert.throws(() => parseDuration("30x"), Error, "unknown unit is rejected");
assert.throws(() => parseDuration("1m1h"), Error, "wrong order is rejected");
assert.throws(() => parseDuration("1h1h"), Error, "repeated unit is rejected");
assert.throws(() => parseDuration("h"), Error, "missing value is rejected");
assert.throws(() => parseDuration(42), Error, "non-string is rejected");
console.log("ok");
