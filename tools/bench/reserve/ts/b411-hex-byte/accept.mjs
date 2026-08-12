import assert from "node:assert/strict";
import { byteHex, bytesHex } from "./solution.ts";

assert.equal(byteHex(0), "00", "nothing is still two digits");
assert.equal(byteHex(255), "ff", "the largest value");
assert.equal(byteHex(16), "10", "the second digit rolls over");
assert.equal(bytesHex([0, 255]), "00ff", "two values run together");
assert.equal(bytesHex([]), "", "no values at all");
assert.equal(bytesHex([1]), "01", "one value keeps its leading zero");
console.log("ok");
