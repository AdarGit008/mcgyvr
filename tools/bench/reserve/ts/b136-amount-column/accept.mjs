import assert from "node:assert/strict";
import { totalAmounts } from "./solution.ts";

assert.equal(totalAmounts(["1", "2"]), "3", "two whole amounts");
assert.equal(totalAmounts(["1.5", "2.25"]), "3.75", "fractions align to the longest");
assert.equal(totalAmounts(["0.99", "0.01"]), "1.00", "carry crosses the dot");
assert.equal(totalAmounts(["999", "1"]), "1_000", "grouping appears in the total");
assert.equal(totalAmounts(["1_204.50"]), "1_204.50", "a lone amount comes back normalised");
assert.equal(
  totalAmounts(["9007199254740993", "0"]),
  "9_007_199_254_740_993",
  "amounts beyond float precision stay exact",
);
assert.equal(totalAmounts(["0", "0"]), "0", "all zero stays zero");
assert.equal(totalAmounts(["2", "0.125"]), "2.125", "whole plus three fraction digits");
assert.equal(totalAmounts(["4_5", "5"]), "50", "input grouping need not be in threes");
assert.throws(() => totalAmounts(42), Error, "non-list argument is rejected");
assert.throws(() => totalAmounts([]), Error, "empty list is rejected");
assert.throws(() => totalAmounts(["1", 2]), Error, "non-string amount is rejected");
assert.throws(() => totalAmounts([""]), Error, "empty amount is rejected");
assert.throws(() => totalAmounts([".5"]), Error, "no digit before the dot is rejected");
assert.throws(() => totalAmounts(["5."]), Error, "no digit after the dot is rejected");
assert.throws(() => totalAmounts(["1__2"]), Error, "doubled underscore is rejected");
assert.throws(() => totalAmounts(["1.2_3"]), Error, "underscore in the fraction is rejected");
assert.throws(() => totalAmounts(["-3"]), Error, "stray character is rejected");
console.log("ok");
