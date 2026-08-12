import assert from "node:assert/strict";
import { tintMix } from "./solution.ts";

assert.equal(tintMix(100, 10, 100, 20), 15, "equal volumes meet in the middle");
assert.equal(tintMix(0, 0, 0, 0), 0, "two empty tins");
assert.equal(tintMix(50, 10, 150, 50), 40, "the larger tin pulls harder");
assert.equal(tintMix(100, 10, 0, 90), 10, "an empty second tin changes nothing");
assert.equal(tintMix(3, 10, 4, 20), 15, "rounded down from a fraction");
assert.equal(tintMix(1, 99, 1, 100), 99, "a half rounds down");
console.log("ok");
