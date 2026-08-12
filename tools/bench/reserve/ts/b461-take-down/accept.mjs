import assert from "node:assert/strict";
import { takeDown } from "./solution.ts";

assert.equal(takeDown(10, 3), 7, "three taken from ten");
assert.equal(takeDown(10, 10), 0, "everything taken");
assert.equal(takeDown(10, 0), 10, "nothing taken");
assert.equal(takeDown(0, 0), 0, "nothing held and nothing taken");
assert.equal(takeDown(5, 1), 4, "one taken from five");
assert.throws(() => takeDown(5, 6), Error, "taking too much is rejected");
console.log("ok");
