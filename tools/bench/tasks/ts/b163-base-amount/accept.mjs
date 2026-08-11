import assert from "node:assert/strict";
import { baseAmount } from "./solution.ts";

const DEFS = { bale: [4, "ream"], ream: [20, "quire"], quire: [25, "sheet"] };

assert.equal(baseAmount(7, "sheet", DEFS, "sheet"), 7, "the base unit is already converted");
assert.equal(baseAmount(3, "quire", DEFS, "sheet"), 75, "one definition unwinds");
assert.equal(baseAmount(2, "ream", DEFS, "sheet"), 1000, "two definitions unwind");
assert.equal(baseAmount(1, "bale", DEFS, "sheet"), 2000, "the whole chain unwinds");
assert.equal(baseAmount(0, "bale", DEFS, "sheet"), 0, "zero of any unit is zero");
assert.equal(baseAmount(5, "sheet", {}, "sheet"), 5, "empty defs still serve the base unit");
assert.throws(() => baseAmount(-1, "ream", DEFS, "sheet"), Error, "a negative amount is rejected");
assert.throws(() => baseAmount(2.5, "ream", DEFS, "sheet"), Error, "a fractional amount is rejected");
assert.throws(() => baseAmount(1, "box", DEFS, "sheet"), Error, "an unknown unit is rejected");
assert.throws(() => baseAmount(1, "sack", { sack: [0, "sheet"] }, "sheet"), Error, "a zero factor is rejected");
assert.throws(() => baseAmount(1, "loop", { loop: [2, "loop"] }, "sheet"), Error, "a chain that loops is rejected");
console.log("ok");
