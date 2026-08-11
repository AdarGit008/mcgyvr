import assert from "node:assert/strict";
import { shiftStamp } from "./solution.ts";

assert.equal(shiftStamp("09:15", 30), "09:45", "a move inside the hour");
assert.equal(shiftStamp("09:15", 0), "09:15", "a move of nothing holds the stamp");
assert.equal(shiftStamp("09:45", 30), "10:15", "a move rolls into the next hour");
assert.equal(shiftStamp("23:50", 20), "00:10", "a move past midnight wraps");
assert.equal(shiftStamp("00:05", -10), "23:55", "a backward move wraps the other way");
assert.equal(shiftStamp("07:30", -1440), "07:30", "a whole day back lands on itself");
assert.equal(shiftStamp("12:00", 4325), "12:05", "an offset of several days still wraps");
assert.throws(() => shiftStamp("7:05", 5), Error, "a one-digit hour is rejected");
assert.throws(() => shiftStamp("24:00", 5), Error, "an hour above 23 is rejected");
assert.throws(() => shiftStamp("10:60", 5), Error, "a minute above 59 is rejected");
assert.throws(() => shiftStamp(1015, 5), Error, "a stamp that is not a string is rejected");
assert.throws(() => shiftStamp("10:15", 1.5), Error, "a fractional offset is rejected");
console.log("ok");
