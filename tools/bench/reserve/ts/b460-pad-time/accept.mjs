import assert from "node:assert/strict";
import { padTime } from "./solution.ts";

assert.equal(padTime(9, 5), "09:05", "both parts are padded");
assert.equal(padTime(12, 30), "12:30", "neither part needs padding");
assert.equal(padTime(0, 0), "00:00", "midnight");
assert.equal(padTime(23, 59), "23:59", "the last minute of the day");
assert.equal(padTime(9, 30), "09:30", "only the hour needs padding");
assert.equal(padTime(12, 5), "12:05", "only the minute needs padding");
console.log("ok");
