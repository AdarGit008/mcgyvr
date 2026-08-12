import assert from "node:assert/strict";
import { timeAdd } from "./solution.ts";

assert.deepEqual(timeAdd(9, 0, 60), [10, 0], "an hour on");
assert.deepEqual(timeAdd(9, 30, 45), [10, 15], "past the hour");
assert.deepEqual(timeAdd(23, 30, 60), [0, 30], "round past midnight");
assert.deepEqual(timeAdd(0, 0, 0), [0, 0], "nothing added");
assert.deepEqual(timeAdd(10, 0, 1440), [10, 0], "a whole day comes back round");
assert.deepEqual(timeAdd(12, 0, 1500), [13, 0], "more than a day");
console.log("ok");
