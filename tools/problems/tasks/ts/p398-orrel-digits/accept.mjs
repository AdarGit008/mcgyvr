import assert from "node:assert/strict";
import { orrelDigits } from "./solution.ts";

assert.equal(orrelDigits(0), "o", "nought is the lone mark");
assert.equal(orrelDigits(1), "i", "one");
assert.equal(orrelDigits(2), "y", "two");
assert.equal(orrelDigits(3), "iyo", "three needs three places");
assert.equal(orrelDigits(5), "iyy", "five");
assert.equal(orrelDigits(9), "ioo", "nine sits on the third place alone");
assert.equal(orrelDigits(-1), "iy", "minus one, with no minus sign");
assert.equal(orrelDigits(-3), "io", "minus three sits on the second place");
assert.equal(orrelDigits(-9), "iyoo", "minus nine");
assert.equal(orrelDigits(100), "ioyoi", "a hundred");
assert.equal(orrelDigits(-100), "iyiiiy", "minus a hundred");
assert.equal(
  orrelDigits(1000000),
  "yiyooyiiiiooi",
  "the largest quantity allowed",
);

assert.throws(() => orrelDigits("4"), Error, "text is not a number");
assert.throws(() => orrelDigits(1.5), Error, "a fraction is not whole");
assert.throws(() => orrelDigits(null), Error, "nothing at all is rejected");
assert.throws(
  () => orrelDigits(1000001),
  Error,
  "a quantity above the cap is rejected",
);
assert.throws(
  () => orrelDigits(-1000001),
  Error,
  "a quantity below the cap is rejected",
);
console.log("ok");
