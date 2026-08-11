import assert from "node:assert/strict";
import { durHours, durText } from "./solution.ts";

assert.equal(durHours(90), 1, "an hour and a half holds one hour");
assert.equal(durHours(59), 0, "under an hour holds none");
assert.equal(durText(90), "1h30m", "both parts are written");
assert.equal(durText(60), "1h", "a whole hour drops the minutes");
assert.equal(durText(30), "30m", "under an hour drops the hours");
assert.equal(durText(0), "0m", "nothing is written 0m");
assert.equal(durText(125), "2h5m", "two hours and a little");
console.log("ok");
