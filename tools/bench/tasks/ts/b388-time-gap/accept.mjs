import assert from "node:assert/strict";
import { timeGap } from "./solution.ts";

assert.equal(timeGap(9, 0, 10, 0), 60, "an hour later");
assert.equal(timeGap(9, 30, 10, 0), 30, "half an hour later");
assert.equal(timeGap(23, 0, 1, 0), 120, "over midnight");
assert.equal(timeGap(10, 0, 10, 0), 1440, "the same time is a whole day");
assert.equal(timeGap(0, 0, 23, 59), 1439, "almost a whole day");
assert.equal(timeGap(9, 0, 9, 30), 30, "within the same hour");
console.log("ok");
