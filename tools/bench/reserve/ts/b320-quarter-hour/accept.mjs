import assert from "node:assert/strict";
import { quarterHour } from "./solution.ts";

assert.equal(quarterHour(20), 15, "brought down to the quarter");
assert.equal(quarterHour(15), 15, "already on a quarter");
assert.equal(quarterHour(14), 0, "just short of the first quarter");
assert.equal(quarterHour(0), 0, "no minutes at all");
assert.equal(quarterHour(59), 45, "the last quarter of the hour");
assert.throws(() => quarterHour(-1), Error, "negative minutes are rejected");
console.log("ok");
