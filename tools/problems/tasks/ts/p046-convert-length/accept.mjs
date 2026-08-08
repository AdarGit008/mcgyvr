import assert from "node:assert/strict";
import { convertLength } from "./solution.ts";

assert.equal(convertLength("1km 250m", "m"), 1250, "kilometres fold into metres");
assert.equal(convertLength("2cm 5mm", "mm"), 25, "centimetres fold into millimetres");
assert.equal(convertLength("5mm 2cm", "mm"), 25, "part order is irrelevant");
assert.equal(convertLength("3m 20m", "m"), 23, "a symbol may recur");
assert.equal(convertLength("3000mm", "m"), 3, "an even conversion upward succeeds");
assert.equal(convertLength("42km", "km"), 42, "identity conversion");
assert.equal(convertLength("0mm", "km"), 0, "zero converts into anything");
assert.equal(convertLength("1km", "mm"), 1000000, "a kilometre is a million millimetres");
assert.throws(() => convertLength("1500mm", "m"), Error, "an uneven conversion refuses");
assert.throws(() => convertLength("5mm", "cm"), Error, "half a centimetre refuses");
assert.throws(() => convertLength("3in", "mm"), Error, "a foreign symbol refuses");
assert.throws(() => convertLength("3 mm", "mm"), Error, "a detached number refuses");
assert.throws(() => convertLength("2m", "yd"), Error, "an unknown target refuses");
assert.throws(() => convertLength("", "m"), Error, "the empty quantity refuses");
console.log("ok");
