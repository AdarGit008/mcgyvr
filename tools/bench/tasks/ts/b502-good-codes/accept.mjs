import assert from "node:assert/strict";
import { goodCodes } from "./solution.ts";

assert.deepEqual(goodCodes(["12", "14"]), ["12"], "only the even total is kept");
assert.deepEqual(goodCodes(["a1b2"]), ["a1b2"], "anything not a figure is passed over");
assert.deepEqual(goodCodes(["9", "33"]), ["9", "33"], "two codes that both divide evenly");
assert.deepEqual(goodCodes(["00"]), ["00"], "a total of nothing divides evenly");
assert.deepEqual(goodCodes(["7"]), [], "no code divides evenly");
assert.deepEqual(goodCodes([]), [], "no codes at all");
console.log("ok");
