import assert from "node:assert/strict";
import { combineFractions } from "./solution.ts";

assert.equal(combineFractions(["1/2", "1/3"]), "5/6", "simple sum");
assert.equal(combineFractions(["1/4", "1/4"]), "1/2", "sum is reduced");
assert.equal(combineFractions(["2/4"]), "1/2", "single entry is reduced");
assert.equal(combineFractions(["1/2", "-1/2"]), "0/1", "zero is 0/1");
assert.equal(combineFractions(["-1/6", "-1/6"]), "-1/3", "negative total");
assert.equal(combineFractions(["3/1", "1/2"]), "7/2", "improper total kept as n/d");
assert.equal(combineFractions(["5/10", "1/10", "2/5"]), "1/1", "whole total keeps /1");
assert.equal(combineFractions(["0/7"]), "0/1", "zero entry normalises");
assert.throws(() => combineFractions([]), Error, "empty list is rejected");
assert.throws(() => combineFractions(["1/0"]), Error, "zero denominator is rejected");
assert.throws(() => combineFractions(["1/-2"]), Error, "signed denominator is rejected");
assert.throws(() => combineFractions(["one/2"]), Error, "non-numeric part is rejected");
assert.throws(() => combineFractions(["1/2", "3"]), Error, "missing slash is rejected");
console.log("ok");
