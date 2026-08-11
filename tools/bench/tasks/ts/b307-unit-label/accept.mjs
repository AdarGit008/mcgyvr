import assert from "node:assert/strict";
import { shortUnit, labelOf } from "./solution.ts";

assert.equal(shortUnit("metre"), "met", "the first three letters");
assert.equal(shortUnit("kg"), "kg", "a short name is already short");
assert.equal(labelOf(1, "metre"), "1 metre", "one takes the singular");
assert.equal(labelOf(2, "metre"), "2 metres", "two takes the plural");
assert.equal(labelOf(0, "metre"), "0 metres", "none takes the plural too");
assert.throws(() => labelOf(-1, "metre"), Error, "a negative amount is rejected");
console.log("ok");
